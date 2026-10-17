"""Boundary and failure cases independent of teammates' implementations."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from backend.db.analytics import daily_distribution
from backend.db.models import Activity, Plan
from backend.db.repository import Repository
from backend.integrations.twilio.ai_bridge import AIBridge
from backend.integrations.twilio.app import create_app
from backend.integrations.twilio.sender import Sender, WindowClosed
from backend.jobs.briefings import enqueue_briefings, generate
from backend.jobs.worker import process_inbox, process_outbox
from backend.tests.test_whatsapp import event, signed_form, settings, user


@pytest.mark.asyncio
async def test_repository_handles_server_page_cap_smaller_than_requested():
    records = [{"id": str(uuid4())} for _ in range(5)]
    def respond(request):
        assert request.headers["authorization"] == "Bearer server-secret"
        assert request.url.params["user_id"] == "eq.owner"
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json=records[offset:offset+2] if request.url.path.endswith("time_entries") else [])
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await Repository(client, "https://db.test", "server-secret").activities("owner")
    assert len(result) == 5


@pytest.mark.asyncio
async def test_scheduler_handles_server_page_cap(user):
    users = [user.model_copy(update={"id": uuid4(), "morning_enabled": True}).model_dump(mode="json") for _ in range(3)]
    async def rows(table, **params):
        offset = int(params["offset"])
        return users[offset:offset+1]
    repo = SimpleNamespace(rows=rows, activities=AsyncMock(return_value=[]), rpc=AsyncMock())
    await enqueue_briefings(repo, datetime(2026, 10, 17, 12, tzinfo=timezone.utc))
    assert repo.rpc.await_count == 3


def test_briefing_orders_events_by_instant_not_offset_string(user):
    rows = [event(title="Later", start_time="2026-10-17T09:00:00-07:00", end_time="2026-10-17T10:00:00-07:00"),
            event(title="Earlier", start_time="2026-10-17T11:00:00-04:00", end_time="2026-10-17T12:00:00-04:00")]
    text = generate("morning", user, rows, datetime(2026, 10, 17, 12, tzinfo=timezone.utc))
    assert text.index("Earlier") < text.index("Later")


@pytest.mark.parametrize("field,value", [("title", "   "), ("external_id", "   ")])
def test_blank_success_fields_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Activity.model_validate(event(**{field: value}))


@pytest.mark.parametrize("overrides,status", [({"MessageSid": "bad"},422), ({"From": "whatsapp:abc"},422), ({"Body": "x"*10001},413)])
def test_bad_signed_input_has_no_side_effect(settings, overrides, status):
    repo = SimpleNamespace(rpc=AsyncMock())
    form, headers = signed_form(settings, **overrides)
    with TestClient(create_app(settings, repo)) as client:
        assert client.post("/api/whatsapp", data=form, headers=headers).status_code == status
    repo.rpc.assert_not_awaited()


def test_json_webhook_is_rejected(settings):
    with TestClient(create_app(settings, SimpleNamespace())) as client:
        assert client.post("/api/whatsapp", json={"Body":"hello"}).status_code == 415
        assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("provider_status,expected", [(401,401),(403,401),(500,503)])
def test_auth_failure_stops_dashboard_queries(settings, provider_status, expected):
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(provider_status,json={})))
    repo = SimpleNamespace(user=AsyncMock())
    with TestClient(create_app(settings, repo, upstream)) as client:
        assert client.get("/api/activities",headers={"Authorization":"Bearer bad"}).status_code == expected
    repo.user.assert_not_awaited()


@pytest.mark.parametrize("route", ["/api/activities","/api/analytics/today","/api/analytics/week","/api/agent-actions"])
def test_every_dashboard_route_requires_auth(settings, route):
    with TestClient(create_app(settings, SimpleNamespace())) as client:
        assert client.get(route).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["parse500","malformed","duplicate_ids","missing_results","wrong_id","nonterminal"])
async def test_ai_rejects_invalid_provider_results(settings, user, failure):
    settings.ai_base_url, settings.ai_service_token = "https://ai.test", SecretStr("internal")
    original = event(status="proposed",external_id=None)
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("parse"):
            if failure == "parse500":
                return httpx.Response(500,json={})
            if failure == "malformed":
                return httpx.Response(200,json={"actions":[{"title":"bad"}]})
            return httpx.Response(200,json={"actions":[original,original] if failure == "duplicate_ids" else [original]})
        result = {**original,"status":"completed","external_id":"google"}
        if failure == "wrong_id": result["id"] = str(uuid4())
        if failure == "nonterminal": result["status"] = "executing"
        return httpx.Response(200,json={"actions":[] if failure == "missing_results" else [result]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises((ValueError,httpx.HTTPStatusError)):
            await AIBridge(client,settings).process(user,{"id":"SM1","body":"Study","created_at":"2026-10-17T12:00:00Z"})
    if failure in {"parse500","malformed","duplicate_ids"}:
        assert calls == ["/api/parse"]


@pytest.mark.asyncio
async def test_attachment_only_does_not_call_ai(settings,user):
    settings.ai_base_url,settings.ai_service_token = "https://ai.test",SecretStr("internal")
    client = SimpleNamespace(post=AsyncMock())
    plan = await AIBridge(client,settings).process(user,{"body":" "})
    assert "attachments" in plan.reply
    client.post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status",[(400,"failed"),(401,"failed"),(429,"failed"),(500,"unknown"),(503,"unknown")])
async def test_outbox_provider_errors_are_visible_without_resending(user,code,status):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=[{"id":"out","user_id":str(user.id),"body":"Hi","kind":"reply"}]),
                           user=AsyncMock(return_value=user),update=AsyncMock())
    response = httpx.Response(code,request=httpx.Request("POST","https://twilio.test"))
    sender = SimpleNamespace(send=AsyncMock(side_effect=httpx.HTTPStatusError("error",request=response.request,response=response)))
    await process_outbox(repo,sender)
    assert repo.update.call_args.kwargs["status"] == status
    sender.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_queued_inbound_message_is_not_processed_after_opt_out(user):
    user.whatsapp_opt_in = False
    repo = SimpleNamespace(rpc=AsyncMock(return_value=[{"id":"SM1","user_id":str(user.id)}]),
                           user=AsyncMock(return_value=user),update=AsyncMock())
    bridge = SimpleNamespace(process=AsyncMock())
    await process_inbox(repo,bridge)
    bridge.process.assert_not_awaited()
    assert repo.update.call_args.kwargs["error_code"] == "opt_out"


def test_empty_analytics_and_failed_events():
    result = daily_distribution([event(status="failed"),event(status="proposed")],date(2026,10,17),"America/New_York")
    assert result["planned_minutes"] == 0
    assert sum(c["percentage"] for c in result["categories"]) == 0


@pytest.mark.asyncio
async def test_scheduler_skips_invalid_profile_and_continues(user):
    valid = user.model_copy(update={"morning_enabled":True}).model_dump(mode="json")
    repo = SimpleNamespace(rows=AsyncMock(side_effect=[[{**valid,"timezone":"invalid/zone"},valid],[]]),
                           activities=AsyncMock(return_value=[]),rpc=AsyncMock())
    await enqueue_briefings(repo,datetime(2026,10,17,12,tzinfo=timezone.utc))
    repo.rpc.assert_awaited_once()


def test_briefing_includes_due_overdue_but_not_completed_or_future_tasks(user):
    tasks = [event(type="task",start_time=None,end_time=None,title=title,due_date=due,completed_at=done)
             for title,due,done in [("Due today","2026-10-17",None),("Overdue","2026-10-16",None),
                                    ("Future","2026-10-18",None),("Already done","2026-10-17","2026-10-17T12:00:00Z")]]
    text = generate("morning",user,tasks,datetime(2026,10,17,12,tzinfo=timezone.utc))
    assert "2 tasks due/overdue" in text
    assert "Due today" in text and "Overdue" in text
    assert "Future" not in text and "Already done" not in text


@pytest.mark.parametrize("day,start,end,hours",[
    (date(2026,3,8),"2026-03-08T00:00:00-05:00","2026-03-09T00:00:00-04:00",23),
    (date(2026,11,1),"2026-11-01T00:00:00-04:00","2026-11-02T00:00:00-05:00",25),
])
def test_analytics_counts_elapsed_hours_on_dst_transition(day,start,end,hours):
    result = daily_distribution([event(start_time=start,end_time=end)],day,"America/New_York")
    assert result["planned_minutes"] == hours*60


@pytest.mark.asyncio
async def test_disabled_briefing_does_not_read_activities(user):
    repo = SimpleNamespace(rows=AsyncMock(side_effect=[[user.model_dump(mode="json")],[]]),
                           activities=AsyncMock(),rpc=AsyncMock())
    await enqueue_briefings(repo,datetime(2026,10,17,12,tzinfo=timezone.utc))
    repo.activities.assert_not_awaited()
    repo.rpc.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_ai_service_token_does_not_call_parse(settings,user):
    settings.ai_base_url = "https://ai.test"
    client = SimpleNamespace(post=AsyncMock())
    with pytest.raises(RuntimeError,match="AI_SERVICE_TOKEN"):
        await AIBridge(client,settings).process(user,{"body":"Study"})
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_owned_http_client_closes_on_lifespan_failure(settings,monkeypatch):
    client = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr("backend.integrations.twilio.app.httpx.AsyncClient",lambda **kw:client)
    app = create_app(settings,SimpleNamespace())
    with pytest.raises(RuntimeError,match="test interruption"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("test interruption")
    client.aclose.assert_awaited_once()
