"""Multi-user Calendar API using Supabase Auth and encrypted per-user tokens.

Supabase handles Google OAuth/PKCE through the Next.js server callback. This API
verifies every Supabase user token and binds the Google grant to that user's
Google identity before saving it. No API route accepts a user ID from the client.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, SecretStr
import requests
from google.oauth2.credentials import Credentials

from .calendar import CalendarAPIError, CalendarValidationError, GoogleCalendarService
from .config import CALENDAR_SCOPES, TASKS_SCOPES, GOOGLE_TOKEN_URI, GoogleConfig, get_google_config
from .oauth import GoogleOAuthService, GoogleReconnectRequired


@dataclass(frozen=True)
class PublicSettings:
    supabase_url: str
    supabase_secret_key: str = field(repr=False)
    encryption_key: str = field(repr=False)
    google: GoogleConfig = field(repr=False)

    def __post_init__(self):
        parsed = urlsplit(self.supabase_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("SUPABASE_URL must be an HTTPS project origin.")
        if not self.supabase_secret_key:
            raise ValueError("SUPABASE_SECRET_KEY is required on the backend.")
        try:
            Fernet(self.encryption_key.encode())
        except (ValueError, TypeError):
            raise ValueError("GOOGLE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key.") from None

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        load_dotenv(Path(__file__).with_name(".env"), override=False)
        return cls(
            supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
            supabase_secret_key=os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            encryption_key=os.environ.get("GOOGLE_TOKEN_ENCRYPTION_KEY", ""),
            google=get_google_config(),
        )


class SupabaseGateway:
    def __init__(self, settings: PublicSettings):
        self.settings = settings
        self.cipher = Fernet(settings.encryption_key.encode())

    def _call(self, method: str, path: str, *, user_token: str | None = None, **kwargs):
        headers = {"apikey": self.settings.supabase_secret_key}
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"
        elif not self.settings.supabase_secret_key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {self.settings.supabase_secret_key}"
        headers.update(kwargs.pop("headers", {}))
        try:
            response = requests.request(method, self.settings.supabase_url + path,
                                        headers=headers, timeout=20, **kwargs)
        except requests.RequestException:
            raise HTTPException(503, "Account storage is unavailable. Try again shortly.") from None
        if user_token and response.status_code in {401, 403}:
            raise HTTPException(401, "Please sign in again.")
        if not response.ok:
            raise HTTPException(503, "Account storage is not ready. Check the backend setup.")
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise HTTPException(503, "Account storage returned an invalid response.") from None

    def user(self, token: str) -> dict:
        user = self._call("GET", "/auth/v1/user", user_token=token)
        try:
            UUID(user["id"])
            if not user.get("email_confirmed_at"):
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise HTTPException(401, "A verified TimeSlice account is required.") from None
        return user

    def load(self, user_id: str) -> dict | None:
        rows = self._call("GET", "/rest/v1/timeslice_google_connections",
                          params={"user_id": f"eq.{user_id}", "select": "user_id,google_sub,credentials_ciphertext", "limit": "1"})
        if not rows:
            return None
        try:
            row = rows[0]
            data = json.loads(self.cipher.decrypt(row["credentials_ciphertext"].encode()))
            # Bind ciphertext to both the database row and its owner. Moving a
            # ciphertext to another user's row must never transfer Google access.
            if data["user_id"] != user_id or data["google_sub"] != row["google_sub"]:
                raise ValueError
            return data
        except (InvalidToken, ValueError, KeyError, TypeError, IndexError):
            raise HTTPException(409, "Calendar connection needs to be set up again.") from None

    def save(self, user_id: str, google_sub: str, credentials: Credentials):
        info = json.loads(credentials.to_json(strip=["client_secret", "id_token"]))
        envelope = {"user_id": user_id, "google_sub": google_sub, "credentials": info}
        ciphertext = self.cipher.encrypt(json.dumps(envelope).encode()).decode()
        self._call("POST", "/rest/v1/timeslice_google_connections",
                   params={"on_conflict": "user_id"},
                   headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                   json={"user_id": user_id, "google_sub": google_sub,
                         "credentials_ciphertext": ciphertext,
                         "updated_at": datetime.now(timezone.utc).isoformat()})

    def delete(self, user_id: str):
        self._call("DELETE", "/rest/v1/timeslice_google_connections",
                   params={"user_id": f"eq.{user_id}"})


def google_subject(user: dict) -> str:
    for identity in user.get("identities", []):
        if identity.get("provider") == "google":
            subject = identity.get("identity_data", {}).get("sub")
            if isinstance(subject, str) and subject:
                return subject
    raise HTTPException(403, "Sign in with Google before connecting Calendar.")


class ProviderTokens(BaseModel):
    service: Literal["calendar", "tasks"] = "calendar"
    access_token: SecretStr
    refresh_token: SecretStr | None = None


def create_public_app(settings: PublicSettings | None = None) -> FastAPI:
    settings = settings or PublicSettings.from_env()
    gateway = SupabaseGateway(settings)
    oauth = GoogleOAuthService(settings.google, required_scopes=CALENDAR_SCOPES)
    app = FastAPI(title="TimeSlice Calendar API", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Default validation errors can echo request bodies containing tokens.
        return JSONResponse({"detail": "Invalid Calendar request."}, status_code=422)

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def current_user(request: Request):
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer ") or len(header) > 16384:
            raise HTTPException(401, "Please sign in to TimeSlice.")
        return gateway.user(header[7:])

    def credentials_for(user: dict):
        record = gateway.load(user["id"])
        if record is None:
            raise HTTPException(409, "Connect Google Calendar in Settings.")
        if record["google_sub"] != google_subject(user):
            raise HTTPException(409, "Reconnect Calendar with your signed-in Google account.")
        info = {**record["credentials"], "client_id": settings.google.client_id,
                "client_secret": settings.google.client_secret, "token_uri": GOOGLE_TOKEN_URI}
        try:
            return record["google_sub"], Credentials.from_authorized_user_info(info)
        except (ValueError, KeyError):
            raise HTTPException(409, "Reconnect Google Calendar in Settings.") from None

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/google/connection")
    def connection(user=Depends(current_user)):
        record = gateway.load(user["id"])
        connected = record is not None and record["google_sub"] == google_subject(user)
        scopes = set(record['credentials'].get('scopes', [])) if connected else set()
        calendar_connected = connected and set(CALENDAR_SCOPES).issubset(scopes)
        tasks_connected = connected and settings.google.enable_tasks and set(TASKS_SCOPES).issubset(scopes)
        return {"connected": calendar_connected, "calendar_connected": calendar_connected,
                "tasks_connected": tasks_connected, "tasks_enabled": settings.google.enable_tasks,
                "email": user.get("email")}

    @app.put("/api/google/connection")
    def connect(tokens: ProviderTokens, user=Depends(current_user)):
        access_token = tokens.access_token.get_secret_value()
        if not access_token or len(access_token) > 16384:
            raise HTTPException(422, "Invalid Google access token.")
        try:
            profile = requests.get("https://openidconnect.googleapis.com/v1/userinfo",
                                   headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
            # Google exposes granted scope and lifetime via its tokeninfo endpoint.
            # Never log this request's URL, response, or exceptions.
            info = requests.get("https://oauth2.googleapis.com/tokeninfo",
                                params={"access_token": access_token}, timeout=20)
            if not profile.ok or not info.ok:
                raise ValueError
            google_user, token_info = profile.json(), info.json()
            subject = google_subject(user)
            if google_user.get("sub") != subject or token_info.get("aud") != settings.google.client_id:
                raise HTTPException(403, "Google account does not match your TimeSlice account.")
            granted = token_info.get("scope", "").split()
            required = TASKS_SCOPES if tokens.service == 'tasks' else CALENDAR_SCOPES
            if tokens.service == 'tasks' and not settings.google.enable_tasks:
                raise HTTPException(409, "Google Tasks is not enabled yet.")
            if not set(required).issubset(granted):
                raise HTTPException(409, "Approve the requested Google permissions and reconnect.")
            previous = gateway.load(user["id"])
            if previous and previous['google_sub'] == subject:
                old_scopes = set(previous['credentials'].get('scopes', [])) & set(CALENDAR_SCOPES + TASKS_SCOPES)
                if not old_scopes.issubset(granted):
                    raise HTTPException(409, "Keep existing Google permissions selected when connecting another service.")
            lifetime = int(token_info["expires_in"])
            if lifetime <= 0:
                raise ValueError
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise HTTPException(401, "Google access could not be verified. Connect again.") from None
        refresh_token = tokens.refresh_token.get_secret_value() if tokens.refresh_token else None
        if not refresh_token:
            previous = gateway.load(user["id"])
            if previous and previous["google_sub"] == subject:
                refresh_token = previous["credentials"].get("refresh_token")
        if not refresh_token:
            raise HTTPException(409, "Google did not grant offline access. Reconnect and approve access.")
        credentials = Credentials(
            token=access_token, refresh_token=refresh_token, token_uri=GOOGLE_TOKEN_URI,
            client_id=settings.google.client_id, client_secret=settings.google.client_secret,
            scopes=granted,
            expiry=(datetime.now(timezone.utc) + timedelta(seconds=lifetime)).replace(tzinfo=None),
        )
        gateway.save(user["id"], subject, credentials)
        return {"connected": True}

    @app.delete("/api/google/connection")
    def disconnect(user=Depends(current_user)):
        gateway.delete(user["id"])
        return {"connected": False}

    @app.get("/api/google/events")
    def events(start_time: datetime, end_time: datetime, user=Depends(current_user)):
        subject, credentials = credentials_for(user)
        calendar = GoogleCalendarService(user_id=user["id"], credentials=credentials, oauth=oauth)
        try:
            raw = calendar.list_events(start_time=start_time, end_time=end_time)
        except GoogleReconnectRequired:
            raise HTTPException(409, "Google access expired. Reconnect Calendar in Settings.") from None
        except CalendarValidationError as error:
            raise HTTPException(422, str(error)) from None
        except CalendarAPIError:
            raise HTTPException(502, "Calendar is temporarily unavailable. Please try again.") from None
        finally:
            try:
                gateway.save(user["id"], subject, credentials)
            finally:
                calendar.close()
        # Leave all-day events distinguishable. The dashboard excludes them from
        # hourly analytics instead of pretending they occupy 24 planned hours.
        return {"events": [{
            "external_id": item.get("id"), "title": item.get("summary", "Untitled event"),
            "start": item.get("start", {}), "end": item.get("end", {}),
            "category": item.get("extendedProperties", {}).get("private", {}).get("timeslice_category"),
            "status": item.get("status"), "transparency": item.get("transparency", "opaque"),
        } for item in raw]}

    return app
