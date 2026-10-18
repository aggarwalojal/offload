from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from xml.etree import ElementTree

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.integrations.twilio.app import create_app
from backend.integrations.twilio.ai_bridge import AIBridge
from backend.integrations.twilio.onboarding import code_hash
from backend.tests.test_whatsapp import settings, user, signed_form


def test_new_sender_receives_dashboard_without_creating_account(settings):
    settings.dashboard_url = "https://dashboard.example"
    repo = SimpleNamespace(rpc=AsyncMock(return_value=False))
    form, headers = signed_form(settings)
    with TestClient(create_app(settings, repo)) as client:
        response = client.post('/api/whatsapp', data=form, headers=headers)
    reply = ElementTree.fromstring(response.text).find('Message').text
    assert 'https://dashboard.example/?view=settings' in reply
    assert 'Nothing has been scheduled' in reply
    assert repo.rpc.await_count == 1
    assert repo.rpc.call_args.args == ('ingest_whatsapp',)


def test_stop_never_triggers_onboarding(settings):
    settings.dashboard_url = 'https://dashboard.example'
    form, headers = signed_form(settings, Body='STOP')
    with TestClient(create_app(settings, SimpleNamespace(rpc=AsyncMock(return_value=False)))) as client:
        response = client.post('/api/whatsapp', data=form, headers=headers)
    assert ElementTree.fromstring(response.text).find('Message') is None


@pytest.mark.parametrize('outcome', ['linked', 'invalid', 'conflict'])
def test_verification_uses_signed_sender_and_hashed_code(settings, outcome):
    code = 'a' * 32
    repo = SimpleNamespace(rpc=AsyncMock(return_value=outcome))
    form, headers = signed_form(settings, Body=f'LINK {code}')
    with TestClient(create_app(settings, repo)) as client:
        response = client.post('/api/whatsapp', data=form, headers=headers)
    repo.rpc.assert_awaited_once_with('consume_whatsapp_link', p_hash=code_hash(code), p_from=form['From'])
    assert ('WhatsApp connected' in response.text) is (outcome == 'linked')


def test_forged_verification_does_not_link(settings):
    repo = SimpleNamespace(rpc=AsyncMock())
    form, headers = signed_form(settings, Body='LINK ' + 'a'*32)
    form['From'] = 'whatsapp:+15559999999'
    with TestClient(create_app(settings, repo)) as client:
        assert client.post('/api/whatsapp', data=form, headers=headers).status_code == 403
    repo.rpc.assert_not_awaited()


@pytest.mark.parametrize('confirmed', [True, False])
def test_challenge_uses_verified_auth_identity_not_client_user_id(settings, confirmed):
    uid = str(uuid4())
    def handle(request):
        assert request.headers['authorization'] == 'Bearer user-token'
        return httpx.Response(200, json={'id': uid, 'email_confirmed_at': '2026-10-17T12:00:00Z' if confirmed else None})
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    repo = SimpleNamespace(rpc=AsyncMock())
    with TestClient(create_app(settings, repo, upstream)) as client:
        response = client.post('/api/whatsapp/link', headers={'Authorization': 'Bearer user-token'},
                               json={'timezone': 'Europe/London', 'user_id': str(uuid4())})
    if not confirmed:
        assert response.status_code == 403
        repo.rpc.assert_not_awaited()
        return
    assert response.status_code == 200
    data = response.json()
    code = data['url'].split('LINK%20')[1]
    assert len(code) == 32
    assert data['expires_in'] == 900
    repo.rpc.assert_awaited_once_with('issue_whatsapp_link', p_user_id=uid, p_hash=code_hash(code), p_timezone='Europe/London')


def test_link_requires_authentication(settings):
    with TestClient(create_app(settings, SimpleNamespace())) as client:
        assert client.post('/api/whatsapp/link', json={}).status_code == 401
        assert client.get('/api/whatsapp/link').status_code == 401


def test_link_status_is_scoped_to_verified_user(settings):
    uid = str(uuid4())
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'id': uid, 'email_confirmed_at': '2026-10-17T12:00:00Z'})))
    repo = SimpleNamespace(rows=AsyncMock(return_value=[{'whatsapp_opt_in': True}]))
    with TestClient(create_app(settings, repo, upstream)) as client:
        response = client.get('/api/whatsapp/link?user_id=someone-else', headers={'Authorization': 'Bearer user-token'})
    assert response.json() == {'connected': True}
    repo.rows.assert_awaited_once_with('users', id=f'eq.{uid}', select='whatsapp_opt_in')


@pytest.mark.parametrize('value', ['http://unsafe.example', 'https://example.com/path', 'https://example.com/?x=1', 'https://user:password@example.com'])
def test_dashboard_url_is_public_origin(settings, value):
    with pytest.raises(ValidationError):
        type(settings)(**{**settings.model_dump(), 'dashboard_url': value}, _env_file=None)


@pytest.mark.asyncio
async def test_existing_user_greeting_includes_dashboard(settings, user):
    settings.dashboard_url = 'https://dashboard.example'
    result = await AIBridge(None, settings).process(user, {'body': 'hello'})
    assert 'https://dashboard.example/?view=settings' in result.reply
    assert result.actions == []


def test_database_link_ownership_expiry_and_rls(postgres):
    postgres.sql('truncate auth.users cascade')
    first, second = str(uuid4()), str(uuid4())
    postgres.sql(f"insert into auth.users values ('{first}'),('{second}')")
    one, two, three = code_hash('first'), code_hash('second'), code_hash('third')
    def issue(uid, digest):
        postgres.sql(f"set role service_role; select public.issue_whatsapp_link('{uid}','{digest}','America/New_York')")
    def consume(digest, phone='whatsapp:+15551111111'):
        return postgres.sql(f"set role service_role; select public.consume_whatsapp_link('{digest}','{phone}')")
    issue(first, one)
    issue(first, three)
    assert consume(one) == 'invalid'  # Reissuing invalidates old codes.
    issue(first, one)
    assert consume(one) == 'linked'
    assert consume(one) == 'invalid'  # Single-use.
    issue(second, two)
    assert consume(two) == 'conflict'  # Cannot take another account's number.
    assert postgres.sql(f"select id from public.users where whatsapp_number='whatsapp:+15551111111'") == first
    assert consume(two, 'whatsapp:+15552222222') == 'linked'
    postgres.sql(f"update public.users set whatsapp_opt_in=false where id='{second}'")
    issue(second, two)
    assert consume(two, 'whatsapp:+15552222222') == 'linked'
    assert postgres.sql(f"select whatsapp_opt_in from public.users where id='{second}'") == 't'
    issue(first, three)
    assert consume(three, 'whatsapp:+15553333333') == 'conflict'  # No silent phone reassignment.
    postgres.sql(f"update public.whatsapp_link_codes set expires_at=now()-interval '1 second' where user_id='{first}'")
    assert consume(three) == 'invalid'
    assert postgres.sql("select has_table_privilege('authenticated','public.whatsapp_link_codes','select')") == 'f'
    assert postgres.sql("select has_function_privilege('anon','public.consume_whatsapp_link(text,text)','execute')") == 'f'
    assert postgres.sql("select whatsapp_opt_in from public.users limit 1") == 't'
