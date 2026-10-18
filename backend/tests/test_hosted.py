import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.hosted import create_hosted_app, hosted_settings
from backend.tests.test_whatsapp import settings


async def idle_worker(settings):
    await asyncio.Event().wait()


def test_hosted_worker_health_and_shutdown(settings):
    cancelled = []
    async def worker(config):
        assert config is settings
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
    with TestClient(create_hosted_app(settings, worker_runner=worker)) as client:
        result = client.get('/health')
        assert result.status_code == 200
        assert result.json()['worker_running'] is True
        assert result.json()['webhook_url'] == settings.twilio_webhook_url
    assert cancelled == [True]


def test_worker_crash_makes_health_unavailable(settings):
    async def stopped_worker(config):
        return
    with TestClient(create_hosted_app(settings, worker_runner=stopped_worker)) as client:
        assert client.get('/health').status_code == 503


def test_parser_requires_shared_token_and_hides_provider_errors(settings):
    settings.ai_service_token = SecretStr('internal-secret')
    with patch('backend.hosted.parse_message', side_effect=RuntimeError('private-provider-content')), \
         TestClient(create_hosted_app(settings, worker_runner=idle_worker)) as client:
        assert client.post('/api/parse', json={'message': 'Study'}).status_code == 401
        response = client.post('/api/parse', json={'message': 'Study'},
                               headers={'Authorization': 'Bearer internal-secret'})
        assert response.status_code == 502
        assert 'private-provider-content' not in response.text


def test_public_origin_does_not_trust_request_headers(monkeypatch):
    monkeypatch.setenv('OFFLOAD_PUBLIC_URL', 'https://backend.example/')
    monkeypatch.setenv('PORT', '10000')
    monkeypatch.setenv('GEMINI_API_KEY', 'private-gemini-key')
    with patch('backend.hosted.Settings') as factory:
        factory.return_value.ai_service_token = SecretStr('internal-secret')
        hosted_settings()
        assert factory.call_args.kwargs['twilio_webhook_url'] == 'https://backend.example/api/whatsapp'
        assert factory.call_args.kwargs['ai_base_url'] == 'http://127.0.0.1:10000'


@pytest.mark.parametrize('url', ['http://public.example', 'https://public.example/path', 'https://user:pass@public.example'])
def test_invalid_public_origin_is_rejected(monkeypatch, url):
    monkeypatch.setenv('OFFLOAD_PUBLIC_URL', url)
    with pytest.raises(RuntimeError, match='HTTPS origin'):
        hosted_settings()
