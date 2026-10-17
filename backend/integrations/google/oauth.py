"""Google OAuth service for a single-process TimeSlice demo.

The HTTP layer must supply the authenticated TimeSlice user ID and an opaque,
server-validated browser session ID to BOTH authorization methods. Never take
these IDs from callback query parameters. Register one service instance for the
application lifetime; pending flows expire after ten minutes and are single use.

This module returns credentials to the backend caller only. The database layer
must encrypt and store them per user; do not return them in an HTTP response.
No Calendar or Tasks writes occur here.
"""

from dataclasses import dataclass, field
from hashlib import sha256
import secrets
from threading import Lock
from time import monotonic

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

from .config import GOOGLE_TOKEN_URI, GoogleConfig


class GoogleOAuthError(RuntimeError):
    """A safe, user-facing OAuth error without provider payloads or tokens."""


class InvalidOAuthState(GoogleOAuthError):
    """The callback is expired, replayed, or does not belong to this session."""


class GoogleConsentDenied(GoogleOAuthError):
    """The user declined Google's consent screen."""


class GoogleReconnectRequired(GoogleOAuthError):
    """The account must be connected again before background access can work."""


@dataclass
class _PendingAuthorization:
    user_id: str = field(repr=False)
    session_hash: str = field(repr=False)
    flow: Flow = field(repr=False)
    expires_at: float


def _session_hash(user_id: str, session_id: str) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise GoogleOAuthError("An authenticated TimeSlice user is required.")
    if not isinstance(session_id, str) or not session_id.strip():
        raise GoogleOAuthError("A verified browser session is required.")
    return sha256(session_id.encode("utf-8")).hexdigest()


class GoogleOAuthService:
    """Short-lived OAuth flows bound to an existing app user and session.

    The in-memory store is for one backend process. Multiple workers require a
    shared server-side store with atomic consumption, expiry, and protected PKCE
    verifiers. These synchronous network methods belong in FastAPI sync routes
    or a thread pool, rather than directly in an async event loop.
    """

    def __init__(self, config: GoogleConfig, *, required_scopes: tuple[str, ...] | None = None):
        self.config = config
        self.required_scopes = config.scopes if required_scopes is None else required_scopes
        self._pending: dict[str, _PendingAuthorization] = {}
        self._lock = Lock()

    def begin_authorization(self, *, user_id: str, session_id: str) -> str:
        """Return a Google consent URL; keep the flow and PKCE verifier private."""
        session_hash = _session_hash(user_id, session_id)
        state = secrets.token_urlsafe(32)
        flow = Flow.from_client_config(
            self.config.oauth_client_config(),
            scopes=list(self.config.scopes),
            redirect_uri=self.config.redirect_uri,
            state=state,
            autogenerate_code_verifier=True,
        )
        url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        now = monotonic()
        with self._lock:
            self._pending = {
                key: pending for key, pending in self._pending.items()
                if pending.expires_at > now
            }
            if len(self._pending) >= 1000:
                raise GoogleOAuthError("Too many pending sign-ins. Try again shortly.")
            self._pending[state] = _PendingAuthorization(
                user_id=user_id,
                session_hash=session_hash,
                flow=flow,
                expires_at=now + 600,
            )
        return url

    def complete_authorization(
        self,
        *,
        user_id: str,
        session_id: str,
        state: str,
        code: str | None = None,
        error: str | None = None,
    ) -> Credentials:
        """Validate and consume callback state before exchanging an auth code.

        Pass only the callback's code, state, and error parameters. Never pass an
        arbitrary callback URL to the token client. An unsuccessful exchange also
        consumes the flow: start a new sign-in rather than replaying the callback.
        """
        session_hash = _session_hash(user_id, session_id)
        if not isinstance(state, str) or not state or len(state) > 256:
            raise InvalidOAuthState("Invalid sign-in session. Please reconnect Google.")
        with self._lock:
            pending = self._pending.get(state)
            if pending is not None and pending.expires_at <= monotonic():
                del self._pending[state]
                pending = None
            if (
                pending is None
                or pending.user_id != user_id
                or not secrets.compare_digest(pending.session_hash, session_hash)
            ):
                raise InvalidOAuthState("Invalid sign-in session. Please reconnect Google.")
            del self._pending[state]

        if error == "access_denied":
            raise GoogleConsentDenied("Google connection was cancelled. You can try again.")
        if error is not None:
            raise GoogleOAuthError("Google could not complete sign-in. Please try again.")
        if not isinstance(code, str) or not code.strip():
            raise GoogleOAuthError("Google did not return an authorization code.")
        try:
            pending.flow.fetch_token(code=code, timeout=30)
            credentials = pending.flow.credentials
        except (OAuth2Error, GoogleAuthError, RequestException, ValueError, KeyError, Warning):
            raise GoogleOAuthError(
                "Google sign-in could not be completed. Please reconnect and try again."
            ) from None

        self._check_scopes(credentials)
        if not credentials.token:
            raise GoogleOAuthError("Google did not return an access token.")
        if not credentials.refresh_token:
            raise GoogleReconnectRequired(
                "Google did not grant offline access. Reconnect and approve access."
            )
        return credentials

    def refresh_credentials(self, credentials: Credentials) -> Credentials:
        """Refresh when necessary; the caller must persist updated credentials.

        The caller retrieves credentials from the authenticated user's protected
        token record. Do not accept serialized credentials from an HTTP client.
        """
        if (
            credentials.client_id != self.config.client_id
            or credentials.token_uri != GOOGLE_TOKEN_URI
        ):
            raise GoogleReconnectRequired("Google credentials do not match this application.")
        self._check_scopes(credentials)
        if credentials.valid:
            return credentials
        if not credentials.refresh_token:
            raise GoogleReconnectRequired("Google access has expired. Please reconnect.")
        try:
            # google-auth supplies a timeout by default; use a bounded request
            # explicitly for the hackathon server's synchronous refresh calls.
            credentials.refresh(_TimeoutRequest())
        except (GoogleAuthError, RequestException, ValueError):
            raise GoogleReconnectRequired(
                "Google access could not be refreshed. Please reconnect and try again."
            ) from None
        self._check_scopes(credentials)
        if not credentials.valid:
            raise GoogleReconnectRequired("Google access is unavailable. Please reconnect.")
        return credentials

    def _check_scopes(self, credentials: Credentials) -> None:
        granted = credentials.granted_scopes
        if granted is None:
            granted = credentials.scopes or ()
        if isinstance(granted, str):
            granted = granted.split()
        if not set(self.required_scopes).issubset(set(granted)):
            raise GoogleReconnectRequired(
                "Required Google permissions were not granted. Reconnect and approve access."
            )


class _TimeoutRequest(Request):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = 30
        return super().__call__(*args, **kwargs)
