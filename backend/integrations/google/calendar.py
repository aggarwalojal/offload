"""Personal Calendar operations for trusted TimeSlice backend callers.

OAuth consent alone does not authorize writes. The backend must validate the
user's intent and build an approved CalendarAction. Never deserialize approval
or user identity directly from an untrusted request or an AI-generated plan.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal
from urllib.parse import quote

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from requests.exceptions import RequestException

from .oauth import GoogleOAuthService, GoogleReconnectRequired


CATEGORIES = frozenset({"academics", "career", "social", "health", "admin"})
_BASE_URL = "https://www.googleapis.com/calendar/v3"


class CalendarValidationError(ValueError):
    """An action is incomplete or invalid; no Google write was attempted."""


class CalendarAuthorizationError(PermissionError):
    """The trusted backend has not authorized this user's exact action."""


class CalendarAPIError(RuntimeError):
    """Safe error without provider response bodies, event text, or tokens."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CalendarConflictError(CalendarAPIError):
    """An event changed or an action ID was reused with different contents."""


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CalendarValidationError(f"{name} is required.")


def _validate_window(start: datetime, end: datetime) -> None:
    for value in (start, end):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise CalendarValidationError("Start and end must be timezone-aware datetimes.")
    # Compare UTC instants, including when a window crosses a DST transition.
    if end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
        raise CalendarValidationError("End must be later than start.")


@dataclass(frozen=True)
class CalendarEventInput:
    title: str
    category: str
    start_time: datetime
    end_time: datetime
    description: str = field(default="", repr=False)

    def __post_init__(self):
        _nonempty(self.title, "title")
        if self.category not in CATEGORIES:
            raise CalendarValidationError("Unknown TimeSlice category.")
        if not isinstance(self.description, str):
            raise CalendarValidationError("description must be text.")
        _validate_window(self.start_time, self.end_time)

    def google_body(self) -> dict[str, Any]:
        return {
            "summary": self.title.strip(),
            "description": self.description,
            "start": {"dateTime": self.start_time.isoformat()},
            "end": {"dateTime": self.end_time.isoformat()},
            "extendedProperties": {"private": {"timeslice_category": self.category}},
        }


@dataclass(frozen=True)
class CalendarAction:
    """Local write contract; approval is supplied by the trusted backend only.

    Reuse action_id when retrying a create, but never for a different activity.
    For updates/deletes, event_id and expected_etag must come from the exact
    calendar event reviewed by the user. Updates specify a complete new timed
    activity, while preserving unrelated Google event fields.
    """

    action_id: str
    user_id: str = field(repr=False)
    operation: Literal["create", "update", "delete"]
    approved: bool = False
    calendar_id: str = "primary"
    event: CalendarEventInput | None = field(default=None, repr=False)
    event_id: str | None = None
    expected_etag: str | None = None

    def __post_init__(self):
        for name in ("action_id", "user_id", "calendar_id"):
            _nonempty(getattr(self, name), name)
        if self.operation not in {"create", "update", "delete"}:
            raise CalendarValidationError("Unknown Calendar operation.")
        if not isinstance(self.approved, bool):
            raise CalendarValidationError("approved must be a boolean.")
        if self.operation in {"create", "update"} and not isinstance(self.event, CalendarEventInput):
            raise CalendarValidationError("A validated event is required.")
        if self.operation == "create":
            if self.event_id is not None or self.expected_etag is not None:
                raise CalendarValidationError("Create actions cannot target an existing event.")
        else:
            _nonempty(self.event_id, "event_id")
            _nonempty(self.expected_etag, "expected_etag")
        if self.operation == "delete" and self.event is not None:
            raise CalendarValidationError("Delete actions must not include event contents.")


@dataclass(frozen=True)
class CalendarResult:
    external_id: str
    calendar_id: str
    status: str = "completed"
    event: dict[str, Any] | None = field(default=None, repr=False)


def calendar_event_id(user_id: str, calendar_id: str, action_id: str) -> str:
    """Stable Google event ID for safe create retries and availability checks."""
    identity = json.dumps([user_id, calendar_id, action_id])
    return hashlib.sha256(identity.encode()).hexdigest()


class GoogleCalendarService:
    """One service per user's stored credentials; never share it across users.

    Read results are Google event dictionaries, preserving all-day `date` values,
    recurring instance IDs, metadata and etags. They are not analytics entries;
    normalization and overlapping-time accounting belong to the database layer.
    """

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

    def list_events(
        self, *, start_time: datetime, end_time: datetime, calendar_id: str = "primary"
    ) -> list[dict[str, Any]]:
        """Read every page of non-deleted events overlapping [start, end).

        Google expands recurring events. All-day events retain their exclusive
        end dates; callers must use the user's timezone when normalizing them.
        This does not check availability or authorize subsequent writes.
        """
        _validate_window(start_time, end_time)
        path = self._events_path(calendar_id)
        params = {
            "timeMin": start_time.isoformat(),
            "timeMax": end_time.isoformat(),
            "singleEvents": "true",
            "showDeleted": "false",
            "orderBy": "startTime",
            "maxResults": 2500,
        }
        events = []
        seen_tokens = set()
        while True:
            page = self._request("GET", path, params=params)
            items = page.get("items", [])
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise CalendarAPIError("Google returned an invalid event list.")
            events.extend(item for item in items if item.get("status") != "cancelled")
            token = page.get("nextPageToken")
            if not token:
                return events
            if not isinstance(token, str) or token in seen_tokens:
                raise CalendarAPIError("Google returned invalid pagination information.")
            seen_tokens.add(token)
            params = {**params, "pageToken": token}

    def get_event(self, event_id: str, *, calendar_id: str = "primary") -> dict[str, Any]:
        _nonempty(event_id, "event_id")
        return self._request("GET", self._events_path(calendar_id) + "/" + quote(event_id, safe=""))

    def execute(self, action: CalendarAction) -> CalendarResult:
        """Execute only an explicitly approved action for this service's user."""
        if not isinstance(action, CalendarAction):
            raise CalendarValidationError("A validated CalendarAction is required.")
        if action.approved is not True or action.user_id != self.user_id:
            raise CalendarAuthorizationError("This Calendar action is not authorized for this user.")
        path = self._events_path(action.calendar_id)
        if action.operation == "create":
            return self._create(action, path)

        path += "/" + quote(action.event_id, safe="")
        # Conditional writes protect against changing an event after the user
        # reviewed it. A 412 means read again and obtain approval for the change.
        headers = {"If-Match": action.expected_etag}
        current = self.get_event(action.event_id, calendar_id=action.calendar_id)
        if current.get("etag") != action.expected_etag:
            raise CalendarConflictError("The event changed. Review it before trying again.", status_code=412)
        # This milestone only supports personal, standalone timed events.
        # Converting all-day events or editing recurring series needs its own UI.
        if current.get("recurrence") or current.get("recurringEventId") or current.get("attendees"):
            raise CalendarValidationError("Only personal, non-recurring events can be modified here.")
        if action.operation == "delete":
            self._request("DELETE", path, headers=headers, params={"sendUpdates": "none"})
            return CalendarResult(external_id=action.event_id, calendar_id=action.calendar_id)
        if "date" in current.get("start", {}) or "date" in current.get("end", {}):
            raise CalendarValidationError("All-day event updates are not supported yet.")
        body = action.event.google_body()
        private = dict(current.get("extendedProperties", {}).get("private", {}))
        private.update(body["extendedProperties"]["private"])
        body["extendedProperties"]["private"] = private
        event = self._request(
            "PATCH", path, json=body, headers=headers, params={"sendUpdates": "none"}
        )
        self._require_event_id(event, action.event_id)
        return CalendarResult(external_id=action.event_id, calendar_id=action.calendar_id, event=event)

    def _create(self, action: CalendarAction, path: str) -> CalendarResult:
        # Hex digits are a subset of Google's base32hex event-ID alphabet.
        # Deterministic IDs make a retry after a lost response safe from duplicates.
        event_id = calendar_event_id(self.user_id, action.calendar_id, action.action_id)
        body = action.event.google_body()
        fingerprint = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        body["id"] = event_id
        body["extendedProperties"]["private"].update({
            "timeslice_action_id": action.action_id,
            "timeslice_payload_hash": fingerprint,
        })
        try:
            event = self._request("POST", path, json=body, params={"sendUpdates": "none"})
        except CalendarConflictError as error:
            if error.status_code != 409:
                raise
            event = self.get_event(event_id, calendar_id=action.calendar_id)
            private = event.get("extendedProperties", {}).get("private", {})
            if (
                event.get("status") == "cancelled"
                or private.get("timeslice_action_id") != action.action_id
                or private.get("timeslice_payload_hash") != fingerprint
            ):
                raise CalendarConflictError(
                    "This action ID already belongs to a different or deleted event.", status_code=409
                ) from None
        self._require_event_id(event, event_id)
        return CalendarResult(external_id=event_id, calendar_id=action.calendar_id, event=event)

    @staticmethod
    def _events_path(calendar_id: str) -> str:
        _nonempty(calendar_id, "calendar_id")
        return f"/calendars/{quote(calendar_id, safe='')}/events"

    @staticmethod
    def _require_event_id(event: dict[str, Any], expected: str) -> None:
        if event.get("id") != expected:
            raise CalendarAPIError("Google returned an unexpected event ID. Check sync status.")

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        self.oauth.refresh_credentials(self.credentials)
        try:
            response = self._session.request(method, _BASE_URL + path, timeout=30, **kwargs)
        except GoogleAuthError:
            raise GoogleReconnectRequired("Google access has expired. Please reconnect.") from None
        except RequestException:
            raise CalendarAPIError(
                "Google Calendar could not be reached. For writes, check sync status before retrying."
            ) from None
        status = response.status_code
        if status == 401:
            raise GoogleReconnectRequired("Google access has expired. Please reconnect.")
        if status in {409, 412}:
            raise CalendarConflictError("The event already exists or has changed.", status_code=status)
        if not 200 <= status < 300:
            message = {
                403: "Google Calendar access was denied. Check permissions and API quotas.",
                404: "The calendar or event could not be found.",
                410: "The event is no longer available.",
                429: "Google Calendar is busy. Please try again later.",
            }.get(status, "Google Calendar could not complete this request. Check sync status before retrying.")
            raise CalendarAPIError(message, status_code=status)
        if status == 204:
            return {}
        try:
            payload = response.json()
        except ValueError:
            raise CalendarAPIError("Google returned an invalid response. Check sync status.") from None
        if not isinstance(payload, dict):
            raise CalendarAPIError("Google returned an invalid response. Check sync status.")
        return payload
