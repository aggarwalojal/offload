"""Standalone Eva service; Jia can include the two routers in backend/main.py."""
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.db.repository import Repository
from backend.db.router import router as dashboard_router
from backend.integrations.twilio.config import Settings
from backend.integrations.twilio.webhook import router as whatsapp_router


def create_app(settings=None, repo=None, client=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings()
        app.state.client = client or httpx.AsyncClient(timeout=15)
        app.state.repo = repo or Repository(app.state.client, app.state.settings.supabase_url,
                            app.state.settings.supabase_service_role_key.get_secret_value())
        try:
            yield
        finally:
            if client is None:
                await app.state.client.aclose()

    app = FastAPI(title="TimeSlice WhatsApp & Database", lifespan=lifespan)
    app.include_router(whatsapp_router)
    app.include_router(dashboard_router)

    @app.exception_handler(httpx.HTTPError)
    async def upstream_error(request: Request, exc):
        return JSONResponse(status_code=503, content={"detail": "Upstream service unavailable"})

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "whatsapp-database"}

    return app


app = create_app()
