from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from backend.profile import preferred_name
from backend.integrations.twilio.ai_bridge import AIBridge
from backend.tests.test_whatsapp import settings, user


def test_name_validation():
    assert preferred_name('  Ojal  ') == 'Ojal'
    assert preferred_name('José') == 'José'
    for value in [' ', '<script>', 'Ojal; schedule gym', 'a'*61]:
        with pytest.raises(ValueError): preferred_name(value)


async def test_name_command_saves_only_linked_users_name(settings, user):
    response = httpx.Response(200, json={}, request=httpx.Request('PUT', 'https://db.test'))
    client = SimpleNamespace(put=AsyncMock(return_value=response), post=AsyncMock())
    result = await AIBridge(client, settings).process(user, {'body': 'Call me Ojal'})
    assert result.reply.startswith('Hey, Ojal!')
    assert result.actions == []
    assert str(user.id) in client.put.call_args.args[0]
    assert client.put.call_args.kwargs['json'] == {'user_metadata': {'offload_name': 'Ojal'}}
    client.post.assert_not_awaited()


async def test_personalized_greeting_keeps_dashboard_link(settings, user):
    settings.dashboard_url = 'https://dashboard.example'
    user.display_name = 'Ojal'
    client = SimpleNamespace(post=AsyncMock())
    result = await AIBridge(client, settings).process(user, {'body': 'Hi Offload'})
    assert 'Hey, Ojal!' in result.reply
    assert 'https://dashboard.example/?view=settings' in result.reply
    assert 'TimeSlice' not in result.reply
    client.post.assert_not_awaited()
