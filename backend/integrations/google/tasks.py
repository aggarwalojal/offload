"""Google Tasks operations for trusted TimeSlice backend callers.

Manages task creation, updates, completion, and deletion via the Google Tasks API v1.
Requires explicit backend validation and authorization; never executes unapproved client writes.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal
from urllib.parse import quote

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from requests.exceptions import RequestException

from .oauth import GoogleOAuthService, GoogleReconnectRequired

CATEGORIES = frozenset({"academics", "career", "social", "health", "admin"})
_BASE_URL = "https://tasks.googleapis.com/tasks/v1"


class TaskValidationError(ValueError):
    """An action is incomplete or invalid; no Google write was attempted."""


class TaskAuthorizationError(PermissionError):
    """The trusted backend has not authorized this user's exact action."""


class TaskAPIError(RuntimeError):
    """Safe error without provider response bodies, task text, or tokens."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class TaskConflictError(TaskAPIError):
    """A task changed or was modified since last retrieved."""


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise TaskValidationError(f"{name} is required.")


def _format_due_date(due: date | datetime | str | None) -> str | None:
    """Formats a due date as an RFC 3339 UTC timestamp required by Google Tasks API."""
    if due is None:
        return None
    if isinstance(due, str):
        # YYYY-MM-DD
        try:
            d = date.fromisoformat(due)
            dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT00:00:00.000Z")
        except ValueError:
            raise TaskValidationError("due string must be in YYYY-MM-DD format.")
    elif isinstance(due, datetime):
        utc_dt = due.astimezone(timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    elif isinstance(due, date):
        dt = datetime(due.year, due.month, due.day, tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT00:00:00.000Z")
    raise TaskValidationError("due must be a date, datetime, or YYYY-MM-DD string.")


@dataclass(frozen=True)
class TaskInput:
    """Validated input representation for a Google Task."""

    title: str
    category: str
    notes: str = field(default="", repr=False)
    due: date | datetime | str | None = None

    def __post_init__(self):
        _nonempty(self.title, "title")
        if self.category not in CATEGORIES:
            raise TaskValidationError("Unknown TimeSlice category.")
        if not isinstance(self.notes, str):
            raise TaskValidationError("notes must be text.")
        _format_due_date(self.due)

    def google_body(self) -> dict[str, Any]:
        category_tag = f"[TimeSlice:{self.category}]"
        notes_content = f"{category_tag}\n{self.notes}".strip() if self.notes else category_tag

        body: dict[str, Any] = {
            "title": self.title.strip(),
            "notes": notes_content,
        }
        formatted_due = _format_due_date(self.due)
        if formatted_due is not None:
            body["due"] = formatted_due
        return body


@dataclass(frozen=True)
class TaskAction:
    """Local write contract for Google Tasks.

    Approval is supplied by the trusted backend only. Never deserialize directly
    from client requests.
    """

    action_id: str
    user_id: str = field(repr=False)
    operation: Literal["create", "update", "delete", "complete"]
    approved: bool = False
    task_list_id: str = "@default"
    task: TaskInput | None = field(default=None, repr=False)
    task_id: str | None = None
    expected_etag: str | None = None

    def __post_init__(self):
        for name in ("action_id", "user_id", "task_list_id"):
            _nonempty(getattr(self, name), name)
        if self.operation not in {"create", "update", "delete", "complete"}:
            raise TaskValidationError("Unknown Task operation.")
        if not isinstance(self.approved, bool):
            raise TaskValidationError("approved must be a boolean.")
        if self.operation in {"create", "update"} and not isinstance(self.task, TaskInput):
            raise TaskValidationError("A validated task is required.")
        if self.operation == "create":
            if self.task_id is not None or self.expected_etag is not None:
                raise TaskValidationError("Create actions cannot target an existing task.")
        else:
            _nonempty(self.task_id, "task_id")
        if self.operation in {"delete", "complete"} and self.task is not None:
            raise TaskValidationError("Delete and complete actions must not include task contents.")


@dataclass(frozen=True)
class TaskResult:
    """Outcome of an executed Google Tasks operation."""

    external_id: str
    task_list_id: str
    status: str = "completed"
    task: dict[str, Any] | None = field(default=None, repr=False)


class GoogleTasksService:
    """One service per user's stored credentials; never share across users."""

    def __init__(
        self, *, user_id: str, credentials: Credentials, oauth: GoogleOAuthService
    ):
        _nonempty(user_id, "user_id")
        self.user_id = user_id
        self.credentials = credentials
        self.oauth = oauth
        self._session = AuthorizedSession(credentials, refresh_timeout=30)

    def close(self) -> None:
        self._session.close()

    def list_tasks(
        self,
        *,
        task_list_id: str = "@default",
        show_completed: bool = False,
        show_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        """Reads non-hidden tasks in the specified task list."""
        path = self._tasks_path(task_list_id)
        params: dict[str, Any] = {
            "showCompleted": "true" if show_completed else "false",
            "showDeleted": "true" if show_deleted else "false",
            "showHidden": "false",
            "maxResults": 100,
        }
        tasks: list[dict[str, Any]] = []
        seen_tokens = set()

        while True:
            page = self._request("GET", path, params=params)
            items = page.get("items", [])
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise TaskAPIError("Google returned an invalid task list.")
            tasks.extend(item for item in items if item.get("deleted") is not True)
            token = page.get("nextPageToken")
            if not token:
                return tasks
            if not isinstance(token, str) or token in seen_tokens:
                raise TaskAPIError("Google returned invalid pagination information.")
            seen_tokens.add(token)
            params["pageToken"] = token

    def get_task(self, task_id: str, *, task_list_id: str = "@default") -> dict[str, Any]:
        _nonempty(task_id, "task_id")
        return self._request("GET", f"{self._tasks_path(task_list_id)}/{quote(task_id, safe='')}")

    def execute(self, action: TaskAction) -> TaskResult:
        """Executes only an explicitly approved action for this service's user."""
        if not isinstance(action, TaskAction):
            raise TaskValidationError("A validated TaskAction is required.")
        if action.approved is not True or action.user_id != self.user_id:
            raise TaskAuthorizationError("This Task action is not authorized for this user.")

        path = self._tasks_path(action.task_list_id)

        if action.operation == "create":
            body = action.task.google_body()
            res = self._request("POST", path, json=body)
            new_id = res.get("id")
            if not new_id or not isinstance(new_id, str):
                raise TaskAPIError("Google did not return a valid task ID.")
            return TaskResult(external_id=new_id, task_list_id=action.task_list_id, task=res)

        target_path = f"{path}/{quote(action.task_id, safe='')}"

        if action.operation == "delete":
            self._request("DELETE", target_path)
            return TaskResult(external_id=action.task_id, task_list_id=action.task_list_id)

        if action.operation == "complete":
            # Set status to completed
            res = self._request("PATCH", target_path, json={"status": "completed"})
            return TaskResult(external_id=action.task_id, task_list_id=action.task_list_id, task=res)

        if action.operation == "update":
            body = action.task.google_body()
            res = self._request("PATCH", target_path, json=body)
            return TaskResult(external_id=action.task_id, task_list_id=action.task_list_id, task=res)

        raise TaskValidationError(f"Unsupported operation: {action.operation}")

    @staticmethod
    def _tasks_path(task_list_id: str) -> str:
        _nonempty(task_list_id, "task_list_id")
        return f"/lists/{quote(task_list_id, safe='')}/tasks"

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        self.oauth.refresh_credentials(self.credentials)
        try:
            response = self._session.request(method, _BASE_URL + path, timeout=30, **kwargs)
        except GoogleAuthError:
            raise GoogleReconnectRequired("Google access has expired. Please reconnect.") from None
        except RequestException:
            raise TaskAPIError(
                "Google Tasks could not be reached. For writes, check sync status before retrying."
            ) from None

        status = response.status_code
        if status == 401:
            raise GoogleReconnectRequired("Google access has expired. Please reconnect.")
        if status in {409, 412}:
            raise TaskConflictError("The task has changed or conflicts with existing state.", status_code=status)
        if not 200 <= status < 300:
            message = {
                403: "Google Tasks access was denied. Check permissions and scopes.",
                404: "The task list or task could not be found.",
                429: "Google Tasks is busy. Please try again later.",
            }.get(status, "Google Tasks could not complete this request.")
            raise TaskAPIError(message, status_code=status)
        if status == 204:
            return {}
        try:
            payload = response.json()
        except ValueError:
            raise TaskAPIError("Google returned an invalid response. Check sync status.") from None
        if not isinstance(payload, dict):
            raise TaskAPIError("Google returned an invalid response. Check sync status.")
        return payload
