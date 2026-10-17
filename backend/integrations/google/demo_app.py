"""Local-only Calendar connection page. Run `python -m ...demo_app`.

Browser sessions and Google credentials are held only in process memory. This
is not a deployed multi-user auth system. Mount routes.py into the team's backend
with real identity and secure persistent storage before connecting the live UI.
"""

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
import secrets
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import GoogleConfig, GoogleConfigError, get_google_config
from .oauth import GoogleOAuthService
from .routes import GoogleIdentity, MemoryCredentialStore, create_google_router

_COOKIE = "timeslice_google_demo"


@dataclass
class _BrowserSession:
    user_id: str = field(repr=False)
    csrf: str = field(repr=False)
    expires_at: float


def create_demo_app(config: GoogleConfig | None = None) -> FastAPI:
    if config is None:
        load_dotenv(Path(__file__).with_name(".env"), override=False)
        config = get_google_config()
    if config.client_id.startswith("replace-") or config.client_secret.startswith("replace-"):
        raise GoogleConfigError("Replace the OAuth placeholders in backend/integrations/google/.env first.")
    redirect = urlsplit(config.redirect_uri)
    if (
        redirect.scheme != "http" or redirect.hostname not in {"localhost", "127.0.0.1"}
        or redirect.path != "/api/google/callback"
    ):
        raise GoogleConfigError("The local demo needs an HTTP localhost callback at /api/google/callback.")
    origin = f"{redirect.scheme}://{redirect.netloc}"
    oauth = GoogleOAuthService(config)
    store = MemoryCredentialStore()
    sessions: dict[str, _BrowserSession] = {}
    lock = Lock()
    app = FastAPI(title="TimeSlice · Google Calendar connection", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return HTMLResponse("This connection demo is only available on this computer.", status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = (
            "no-referrer" if request.url.path == "/api/google/callback" else "same-origin"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://accounts.google.com; "
            "frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    def lookup(request: Request):
        session_id = request.cookies.get(_COOKIE, "")
        with lock:
            session = sessions.get(session_id)
            if session is None or session.expires_at <= monotonic():
                sessions.pop(session_id, None)
                raise HTTPException(status_code=401, detail="Open the connection page to start a session.")
        return session_id, session

    async def identity(request: Request) -> GoogleIdentity:
        session_id, session = lookup(request)
        if request.method == "POST":
            if request.headers.get("origin") != origin:
                raise HTTPException(status_code=403, detail="Start the connection from the local page.")
            body = await request.body()
            if len(body) > 4096:
                raise HTTPException(status_code=400, detail="Invalid connection request.")
            try:
                tokens = parse_qs(body.decode("utf-8"), max_num_fields=10).get("csrf", [])
            except (ValueError, UnicodeError):
                raise HTTPException(status_code=400, detail="Invalid connection request.") from None
            if len(tokens) != 1 or not secrets.compare_digest(tokens[0], session.csrf):
                raise HTTPException(status_code=403, detail="Invalid session. Reload the connection page.")
        return GoogleIdentity(user_id=session.user_id, session_id=session_id)

    app.include_router(create_google_router(oauth=oauth, store=store, identity_dependency=identity))

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        session_id = request.cookies.get(_COOKIE, "")
        with lock:
            now = monotonic()
            expired = [key for key, session in sessions.items() if session.expires_at <= now]
            for key in expired:
                del sessions[key]
            if session_id not in sessions:
                if len(sessions) >= 1000:
                    raise HTTPException(status_code=503, detail="Too many sessions. Restart the local demo.")
                session_id = secrets.token_urlsafe(32)
                sessions[session_id] = _BrowserSession(
                    user_id=secrets.token_urlsafe(24), csrf=secrets.token_urlsafe(32), expires_at=now + 28800
                )
            session = sessions[session_id]
        connected = store.get(session.user_id) is not None
        body = (
            '<span class="pill">CONNECTED</span><h1>A little more connected.</h1>'
            '<p>Your Google Calendar is connected to this local session.</p>'
            '<a class="button" href="/api/google/events">Read my next 7 days</a>'
            if connected else
            '<span class="pill">LOCAL CONNECTION TEST</span><h1>Give your plans a place.</h1>'
            '<p>Connect Google Calendar to TimeSlice. Choose your account and approve the requested permissions.</p>'
            '<form action="/api/google/connect" method="post">'
            f'<input type="hidden" name="csrf" value="{escape(session.csrf)}">'
            '<button class="button">Connect Google Calendar</button></form>'
        )
        response = HTMLResponse(_page(body))
        response.set_cookie(_COOKIE, session_id, httponly=True, samesite="lax", max_age=28800)
        return response

    @app.get("/google/connected", response_class=HTMLResponse)
    def connected_page(request: Request):
        _, session = lookup(request)
        if store.get(session.user_id) is None:
            raise HTTPException(status_code=401, detail="Google Calendar is not connected.")
        return HTMLResponse(_page(
            '<span class="pill">CONNECTED</span><h1>Your calendar is ready.</h1>'
            '<p>Google sign-in succeeded. You can now read your real upcoming events.</p>'
            '<a class="button" href="/api/google/events">Read my next 7 days</a>'
        ))

    return app


def _page(body: str) -> str:
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect Calendar · TimeSlice</title>
<style>body{margin:0;background:#101421;color:#edf0fa;font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh}main{max-width:480px;margin:25px;padding:40px;background:#191e2e;border:1px solid #34374d;border-radius:18px}h1{font-size:34px;letter-spacing:-1px;line-height:1.2}p{color:#a2adc4;font-size:15px;line-height:1.8}.logo{color:#c0a8ff;font-size:24px;font-weight:bold;margin-bottom:35px}.pill{font-size:10px;letter-spacing:2px;color:#77d3b2}.button{display:inline-block;background:#b69afa;color:#171126;padding:14px 20px;border:0;border-radius:8px;font-size:14px;font-weight:bold;text-decoration:none;cursor:pointer}small{display:block;color:#8491aa;font-size:11px;line-height:1.8;margin-top:28px}</style></head><body><main><div class="logo">◔ TimeSlice.</div>''' + body + '''<small>Local demo only. Credentials stay in server memory and are lost on restart. Connecting does not create or change any events. This does not connect the deployed Vercel dashboard yet.</small></main></body></html>'''


def main():
    import uvicorn
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    try:
        config = get_google_config()
        app = create_demo_app(config)
    except GoogleConfigError as error:
        raise SystemExit(f"Calendar setup needed: {error}\nSee backend/integrations/google/CONNECT.md") from None
    callback = urlsplit(config.redirect_uri)
    print(f"Open {callback.scheme}://{callback.netloc}/ in Chrome or Safari to connect Calendar.")
    # Never write callback authorization codes or OAuth state to access logs.
    uvicorn.run(app, host="127.0.0.1", port=callback.port or 80, access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
