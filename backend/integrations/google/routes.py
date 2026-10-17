"""Mountable Google connection routes; identity comes from the host backend.

No write endpoint is exposed here. The caller supplies authenticated identity
(and CSRF protection for POSTs), an OAuth service, and a per-user credential store.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google.oauth2.credentials import Credentials

from .calendar import CalendarAPIError, CalendarValidationError, GoogleCalendarService
from .oauth import GoogleOAuthError, GoogleOAuthService, GoogleReconnectRequired


@dataclass(frozen=True)
class GoogleIdentity:
    user_id: str = field(repr=False)
    session_id: str = field(repr=False)


class CredentialStore(Protocol):
    def get(self, user_id: str) -> Credentials | None: ...
    def save(self, user_id: str, credentials: Credentials) -> None: ...


class MemoryCredentialStore:
    """Temporary process memory, suitable for a local demo; no tokens on disk."""

    def __init__(self):
        self._credentials: dict[str, Credentials] = {}
        self._lock = Lock()

    def get(self, user_id: str) -> Credentials | None:
        with self._lock:
            return self._credentials.get(user_id)

    def save(self, user_id: str, credentials: Credentials) -> None:
        with self._lock:
            self._credentials[user_id] = credentials


def create_google_router(
    *,
    oauth: GoogleOAuthService,
    store: CredentialStore,
    identity_dependency: Callable,
    success_path: str = "/google/connected",
) -> APIRouter:
    """The identity dependency MUST use app authentication, never query IDs.

    It must reject CSRF for the connect POST. The demo app provides its own
    localhost-only browser session; production must use TimeSlice authentication.
    Routes are synchronous where they perform Google network calls.
    """
    if not success_path.startswith("/") or success_path.startswith("//") or "\\" in success_path:
        raise ValueError("success_path must be a local absolute path.")
    router = APIRouter(prefix="/api/google", tags=["Google Calendar"])

    @router.post("/connect")
    def connect(identity: GoogleIdentity = Depends(identity_dependency)):
        try:
            url = oauth.begin_authorization(user_id=identity.user_id, session_id=identity.session_id)
        except GoogleOAuthError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        return RedirectResponse(url, status_code=303)

    @router.get("/callback")
    def callback(request: Request, identity: GoogleIdentity = Depends(identity_dependency)):
        values = {}
        for key in ("state", "code", "error"):
            entries = request.query_params.getlist(key)
            if len(entries) > 1:
                raise HTTPException(status_code=400, detail="Duplicate OAuth callback parameters.")
            values[key] = entries[0] if entries else None
        try:
            credentials = oauth.complete_authorization(
                user_id=identity.user_id,
                session_id=identity.session_id,
                state=values["state"],
                code=values["code"],
                error=values["error"],
            )
        except GoogleOAuthError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        store.save(identity.user_id, credentials)
        return RedirectResponse(success_path, status_code=303)

    @router.get("/status")
    def status(identity: GoogleIdentity = Depends(identity_dependency)):
        connected = store.get(identity.user_id) is not None
        return {"connected": connected, "scopes": list(oauth.config.scopes) if connected else []}

    @router.get("/events")
    def events(
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        identity: GoogleIdentity = Depends(identity_dependency),
    ):
        credentials = store.get(identity.user_id)
        if credentials is None:
            raise HTTPException(status_code=401, detail="Connect Google Calendar first.")
        start = start_time or datetime.now(timezone.utc)
        end = end_time or start + timedelta(days=7)
        calendar = GoogleCalendarService(user_id=identity.user_id, credentials=credentials, oauth=oauth)
        try:
            result = calendar.list_events(start_time=start, end_time=end)
        except GoogleReconnectRequired as error:
            raise HTTPException(status_code=401, detail=str(error)) from None
        except CalendarValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except CalendarAPIError as error:
            raise HTTPException(status_code=502, detail=str(error)) from None
        finally:
            # A successful refresh can precede a failed Calendar request.
            store.save(identity.user_id, credentials)
            calendar.close()
        # Return only fields useful to the UI. Tokens and private integration
        # metadata never leave the backend through this endpoint.
        return {"events": [{
            "external_id": event.get("id"),
            "title": event.get("summary", "Untitled event"),
            "start": event.get("start", {}),
            "end": event.get("end", {}),
            "status": event.get("status"),
        } for event in result]}

    return router
