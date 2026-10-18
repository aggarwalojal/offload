"""Always-on Offload backend: signed WhatsApp ingress, AI parser, and queue worker.

Run exactly one Uvicorn process on a persistent host, not a serverless function.
Supabase holds the durable queues; Google writes remain on the existing API.
"""
import asyncio
from contextlib import asynccontextmanager
import os
import secrets
import logging
import httpx
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.integrations.twilio.app import create_app
from backend.integrations.twilio.config import Settings
from backend.jobs.worker import run as run_worker
from backend.main import parse_message
from backend.schemas import ParseRequest, ParseResponse


def hosted_settings():
    public_url = os.environ.get('OFFLOAD_PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL', '')
    parsed = urlsplit(public_url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
        raise RuntimeError('Set OFFLOAD_PUBLIC_URL to the backend HTTPS origin, or deploy using Render’s RENDER_EXTERNAL_URL.')
    try:
        port = int(os.environ.get('PORT', '10000'))
        if not 1 <= port <= 65535:
            raise ValueError
        settings = Settings(twilio_webhook_url=public_url.rstrip('/') + '/api/whatsapp',
            dashboard_url='https://timeslice-dashboard.vercel.app',
            ai_base_url=f'http://127.0.0.1:{port}',
            google_execution_url='https://timeslice-google-api.vercel.app')
    except Exception:
        # Pydantic errors can include credential input values. Do not expose them
        # in deployment logs; operators should check the required variable names.
        raise RuntimeError('Invalid backend environment. Check Supabase and Twilio credentials, AI_SERVICE_TOKEN, and PORT.') from None
    if not settings.ai_service_token.get_secret_value().strip() or not os.environ.get('GEMINI_API_KEY', '').strip():
        raise RuntimeError('Configure AI_SERVICE_TOKEN and GEMINI_API_KEY before starting the hosted backend.')
    return settings


def create_hosted_app(settings=None, repo=None, client=None, worker_runner=None):
    settings = settings or hosted_settings()
    app = create_app(settings, repo, client)
    base_lifespan = app.router.lifespan_context
    async def hosted_worker(config):
        # Uvicorn binds its socket after lifespan startup. Do not claim inbox
        # messages until the loopback parser can accept connections.
        async with httpx.AsyncClient(timeout=5) as probe:
            for _ in range(120):
                try:
                    if (await probe.get(config.ai_base_url + '/health')).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError('Local AI parser did not become reachable.')
            response = await probe.post(config.google_execution_url + '/api/execute', json={},
                headers={'Authorization': 'Bearer ' + config.ai_service_token.get_secret_value()})
            if response.status_code != 422:
                raise RuntimeError('Google execution token is not configured consistently. No queue messages were claimed.')
        logging.getLogger('offload.hosted').info('Shared execution token verified; starting durable queue worker.')
        await run_worker(config)

    runner = worker_runner or hosted_worker

    @asynccontextmanager
    async def lifespan(app):
        async with base_lifespan(app):
            task = asyncio.create_task(runner(settings))
            app.state.queue_worker = task
            def worker_stopped(completed):
                if not completed.cancelled():
                    logging.getLogger('offload.hosted').error('Queue worker stopped. Check shared execution token, loopback parser, and hosting configuration; health is unavailable.')
            task.add_done_callback(worker_stopped)
            try:
                yield
            finally:
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=20)
                except asyncio.TimeoutError:
                    pass

    app.router.lifespan_context = lifespan

    @app.middleware('http')
    async def worker_readiness(request: Request, call_next):
        if request.url.path == '/health':
            task = getattr(app.state, 'queue_worker', None)
            running = task is not None and not task.done()
            return JSONResponse({'status': 'ok' if running else 'unavailable',
                'service': 'offload-hosted', 'worker_running': running,
                'webhook_url': settings.twilio_webhook_url}, status_code=200 if running else 503)
        return await call_next(request)

    def internal_service(request: Request):
        expected = settings.ai_service_token.get_secret_value()
        actual = request.headers.get('authorization', '')
        if not expected or not secrets.compare_digest(actual.encode(), f'Bearer {expected}'.encode()):
            raise HTTPException(401, 'Internal service authentication is required.')

    @app.post('/api/parse', response_model=ParseResponse, dependencies=[Depends(internal_service)])
    def parse(request: ParseRequest):
        try:
            return parse_message(request)
        except Exception:
            raise HTTPException(502, 'Offload could not parse this message. Try again shortly.') from None

    return app
