"""Environment-based configuration for TimeSlice's Google integration.

Load environment variables in the application entry point (or your shell) before
calling get_google_config(). Importing this module requires no credentials and
performs no network requests. OAuth tokens belong in per-user secure storage,
not in this configuration.
"""

from dataclasses import dataclass, field
import os
from typing import Mapping
from urllib.parse import urlsplit


# Restrict event access to calendars the user owns. Tasks access is opt-in until
# the Tasks integration is implemented. No Gmail, Drive, or profile scopes.
CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar.freebusy",
)
TASKS_SCOPES = ("https://www.googleapis.com/auth/tasks",)
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
DEFAULT_REDIRECT_URI = "http://localhost:8000/api/google/callback"


class GoogleConfigError(ValueError):
    """Missing or invalid configuration; messages never include secret values."""


def _validate_redirect_uri(uri: str) -> None:
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError:
        raise GoogleConfigError("GOOGLE_REDIRECT_URI must be a valid URL.") from None

    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (port is not None and port == 0)
    ):
        raise GoogleConfigError(
            "GOOGLE_REDIRECT_URI must have a host and no credentials, query, or fragment."
        )

    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise GoogleConfigError(
            "GOOGLE_REDIRECT_URI requires HTTPS except for local development."
        )


@dataclass(frozen=True)
class GoogleConfig:
    """Validated OAuth settings, safe to include in ordinary diagnostic reprs."""

    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    redirect_uri: str = DEFAULT_REDIRECT_URI
    enable_tasks: bool = False

    def __post_init__(self) -> None:
        for name in ("client_id", "client_secret"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise GoogleConfigError(f"GOOGLE_{name.upper()} is required.")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.enable_tasks, bool):
            raise GoogleConfigError("GOOGLE_ENABLE_TASKS must be a boolean.")
        if not isinstance(self.redirect_uri, str):
            raise GoogleConfigError("GOOGLE_REDIRECT_URI must be a URL string.")
        object.__setattr__(self, "redirect_uri", self.redirect_uri.strip())
        _validate_redirect_uri(self.redirect_uri)

    @property
    def scopes(self) -> tuple[str, ...]:
        return CALENDAR_SCOPES + (TASKS_SCOPES if self.enable_tasks else ())

    def oauth_client_config(self) -> dict[str, dict[str, object]]:
        """Return the format accepted by google_auth_oauthlib.flow.Flow.

        The returned dictionary contains the client secret: never log it or send
        it to the browser. OAuth state validation and per-user token storage are
        responsibilities of the upcoming OAuth handler.
        """
        return {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": GOOGLE_AUTH_URI,
                "token_uri": GOOGLE_TOKEN_URI,
                "redirect_uris": [self.redirect_uri],
            }
        }


def get_google_config(env: Mapping[str, str] | None = None) -> GoogleConfig:
    """Read settings on demand; an explicit mapping makes local tests simple."""
    source = os.environ if env is None else env
    raw_tasks = source.get("GOOGLE_ENABLE_TASKS", "false").strip().lower()
    if raw_tasks not in {"true", "false"}:
        raise GoogleConfigError("GOOGLE_ENABLE_TASKS must be true or false.")
    return GoogleConfig(
        client_id=source.get("GOOGLE_CLIENT_ID", ""),
        client_secret=source.get("GOOGLE_CLIENT_SECRET", ""),
        redirect_uri=source.get("GOOGLE_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        enable_tasks=raw_tasks == "true",
    )
