from datetime import datetime, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.integrations.twilio.demo_poll import InboundPoller, NoDemoReplies, check_access
from backend.integrations.twilio.sender import WindowClosed
from backend.tests.test_whatsapp import settings

SINCE = datetime(2026,10,17,12,tzinfo=timezone.utc)


def message(settings,**changes):
    return {"sid":"SM"+"b"*32,"account_sid":settings.twilio_account_sid,"direction":"inbound",
            "to":settings.twilio_whatsapp_from,"from":"whatsapp:+15551234567","body":"Study",
            "date_created":format_datetime(SINCE),**changes}


@pytest.mark.asyncio
async def test_poll_ingests_real_api_shape_and_preserves_timestamp(settings):
    def respond(request):
        assert request.headers["authorization"].startswith("Basic ")
        assert request.url.params["To"] == settings.twilio_whatsapp_from
        return httpx.Response(200,json={"messages":[message(settings)],"next_page_uri":None})
    repo = SimpleNamespace(rpc=AsyncMock(return_value=True),request=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await InboundPoller(client,repo,settings,SINCE).poll_once() == 1
    assert repo.rpc.call_args.kwargs["p_sid"] == "SM"+"b"*32
    assert repo.request.call_args.kwargs["json"] == {"created_at":SINCE.isoformat()}


@pytest.mark.parametrize("changes",[
    {"direction":"outbound-api"},{"account_sid":"ACother"},{"to":"whatsapp:+15550001111"},
    {"from":"+15551234567"},{"sid":"bad"},{"body":"x"*10001},
    {"date_created":"Fri, 16 Oct 2026 12:00:00 +0000"},
])
async def test_poll_skips_outbound_foreign_old_or_invalid_messages(settings,changes):
    repo = SimpleNamespace(rpc=AsyncMock(),request=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"messages":[message(settings,**changes)]}))) as client:
        await InboundPoller(client,repo,settings,SINCE).poll_once()
    repo.rpc.assert_not_awaited()


async def test_pagination_cannot_leak_twilio_credentials(settings):
    repo = SimpleNamespace(rpc=AsyncMock())
    calls = []
    def respond(request):
        calls.append(request.url.host)
        return httpx.Response(200,json={"messages":[],"next_page_uri":"https://attacker.test/steal"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError,match="pagination"):
            await InboundPoller(client,repo,settings,SINCE).poll_once()
    assert calls == ["api.twilio.com"]


async def test_trial_demo_does_not_attempt_custom_outgoing_reply():
    with pytest.raises(WindowClosed,match="demo_replies_disabled"):
        await NoDemoReplies().send(None,"Hi","reply")


async def test_polled_stop_passes_opt_out(settings):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=True),request=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"messages":[message(settings,body="STOP")]}))) as client:
        await InboundPoller(client,repo,settings,SINCE).poll_once()
    assert repo.rpc.call_args.kwargs["p_opt_out"] is True


async def test_poll_reads_all_pages_then_ingests_in_time_order(settings):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=True),request=AsyncMock())
    requests = []
    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200,json={"messages":[message(settings,sid="SM"+"c"*32,
                date_created="Sat, 17 Oct 2026 12:01:00 +0000")],
                "next_page_uri":f"/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json?PageToken=test"})
        return httpx.Response(200,json={"messages":[message(settings)],"next_page_uri":None})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await InboundPoller(client,repo,settings,SINCE).poll_once()
    assert len(requests) == 2 and requests[1].url.params["PageToken"] == "test"
    assert [call.kwargs["p_sid"] for call in repo.rpc.call_args_list] == ["SM"+"b"*32,"SM"+"c"*32]


async def test_poll_api_access_denied_does_not_ingest(settings):
    repo = SimpleNamespace(rpc=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(403))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await InboundPoller(client,repo,settings,SINCE).poll_once()
    repo.rpc.assert_not_awaited()


async def test_seen_stop_is_not_replayed(settings):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=True),request=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"messages":[message(settings,body="STOP")]}))) as client:
        poller = InboundPoller(client,repo,settings,SINCE)
        assert await poller.poll_once() == 1
        assert await poller.poll_once() == 0
    repo.rpc.assert_awaited_once()


async def test_persistence_failure_can_be_retried(settings):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=True),request=AsyncMock(side_effect=[RuntimeError("db"),None]))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"messages":[message(settings)]}))) as client:
        poller = InboundPoller(client,repo,settings,SINCE)
        with pytest.raises(RuntimeError):
            await poller.poll_once()
        assert await poller.poll_once() == 1
        assert await poller.poll_once() == 0
    assert repo.rpc.await_count == 2


async def test_access_check_is_read_only(settings):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json={"messages":[]})
    repo = SimpleNamespace(rows=AsyncMock(return_value=[{"id":"test"}]),rpc=AsyncMock(),request=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await check_access(client,repo,settings)
    assert all(request.method == "GET" for request in requests)
    repo.rpc.assert_not_awaited()
    repo.request.assert_not_awaited()
