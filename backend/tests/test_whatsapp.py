from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from twilio.request_validator import RequestValidator

from backend.db.analytics import daily_distribution, day_bounds
from backend.db.models import Activity, Plan, User
from backend.integrations.twilio.ai_bridge import AIBridge
from backend.integrations.twilio.app import create_app
from backend.integrations.twilio.config import Settings
from backend.integrations.twilio.sender import Sender, WindowClosed
from backend.jobs.briefings import enqueue_briefings, generate
from backend.jobs.worker import process_inbox, process_outbox


@pytest.fixture
def settings():
    return Settings(_env_file=None, supabase_url="https://example.supabase.co",
                    supabase_service_role_key="test-service-key", twilio_account_sid="AC"+"a"*32,
                    twilio_auth_token="test-auth-token", twilio_webhook_url="https://example.ngrok.app/api/whatsapp",
                    ai_base_url="", ai_service_token="")


@pytest.fixture
def user():
    return User(id=uuid4(), whatsapp_number="whatsapp:+15551234567", whatsapp_opt_in=True,
                last_inbound_at=datetime(2026, 10, 17, 12, tzinfo=timezone.utc))


def signed_form(settings, **overrides):
    form = {"AccountSid": settings.twilio_account_sid, "MessageSid": "SM"+"b"*32,
            "From": "whatsapp:+15551234567", "To": settings.twilio_whatsapp_from,
            "Body": "Study tomorrow", **overrides}
    signature = RequestValidator(settings.twilio_auth_token.get_secret_value()).compute_signature(
        settings.twilio_webhook_url, form)
    return form, {"x-twilio-signature": signature}


def event(**overrides):
    return {"id": str(uuid4()), "type": "event", "title": "Study", "category": "academics",
            "start_time": "2026-10-17T10:00:00-04:00", "end_time": "2026-10-17T12:00:00-04:00",
            "status": "completed", "external_id": "google-event", **overrides}


def test_signed_webhook_acknowledges_after_persistence(settings):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=True))
    form, headers = signed_form(settings, FutureTwilioField="included in signature")
    with TestClient(create_app(settings, repo)) as client:
        response = client.post("/api/whatsapp", data=form, headers=headers)
    assert response.status_code == 200
    assert response.text == "<Response></Response>"
    repo.rpc.assert_awaited_once_with("ingest_whatsapp", p_sid=form["MessageSid"], p_from=form["From"],
                                     p_body=form["Body"], p_opt_out=False)


@pytest.mark.parametrize("tamper", ["body", "signature", "account", "destination"])
def test_webhook_rejects_forgery(settings, tamper):
    repo = SimpleNamespace(rpc=AsyncMock())
    overrides = {"AccountSid": "wrong"} if tamper == "account" else {"To": "wrong"} if tamper == "destination" else {}
    form, headers = signed_form(settings, **overrides)
    if tamper == "body":
        form["Body"] = "tampered"
    if tamper == "signature":
        headers["x-twilio-signature"] = "wrong"
    with TestClient(create_app(settings, repo)) as client:
        assert client.post("/api/whatsapp", data=form, headers=headers).status_code == 403
    repo.rpc.assert_not_awaited()


def test_webhook_database_failure_is_retryable(settings):
    repo = SimpleNamespace(rpc=AsyncMock(side_effect=httpx.ConnectError("unavailable")))
    form, headers = signed_form(settings)
    with TestClient(create_app(settings, repo)) as client:
        assert client.post("/api/whatsapp", data=form, headers=headers).status_code == 503


def test_stop_opts_out(settings):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=True))
    form, headers = signed_form(settings, Body="STOP")
    with TestClient(create_app(settings, repo)) as client:
        assert client.post("/api/whatsapp", data=form, headers=headers).status_code == 200
    assert repo.rpc.call_args.kwargs["p_opt_out"] is True


def test_dashboard_requires_auth(settings):
    with TestClient(create_app(settings, SimpleNamespace())) as client:
        assert client.get("/api/activities").status_code == 401


def test_dashboard_uses_verified_user_identity(settings, user):
    def handle(request):
        assert request.url.path == "/auth/v1/user"
        assert request.headers["authorization"] == "Bearer actual-user-token"
        return httpx.Response(200, json={"id": str(user.id)})
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    repo = SimpleNamespace(user=AsyncMock(return_value=user), activities=AsyncMock(return_value=[]))
    with TestClient(create_app(settings, repo, upstream)) as client:
        response = client.get("/api/activities?user_id=someone-else", headers={"Authorization": "Bearer actual-user-token"})
    assert response.status_code == 200
    repo.activities.assert_awaited_once_with(user.id)


@pytest.mark.parametrize("overrides", [
    {"end_time": "2026-10-17T09:00:00-04:00"},
    {"start_time": "2026-10-17T10:00:00"},
    {"category": "other"}, {"external_id": None},
    {"type": "task"}, {"start_time": None},
])
def test_activity_validation(overrides):
    with pytest.raises(ValidationError):
        Activity.model_validate(event(**overrides))


def test_overlap_and_tasks_do_not_inflate_planned_time():
    rows = [event(), event(category="health", start_time="2026-10-17T11:00:00-04:00",
                          end_time="2026-10-17T13:00:00-04:00"),
            event(type="task", start_time=None, end_time=None)]
    result = daily_distribution(rows, date(2026, 10, 17), "America/New_York")
    values = {r["category"]: r["minutes"] for r in result["categories"]}
    assert result["planned_minutes"] == 180
    assert values["academics"] == values["health"] == 90


def test_same_category_overlaps_are_counted_once():
    result = daily_distribution([event(), event()], date(2026, 10, 17), "America/New_York")
    assert result["planned_minutes"] == 120


@pytest.mark.parametrize("day,hours", [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_dst_day_bounds(day, hours):
    start, end = day_bounds(day, "America/New_York")
    assert (end-start).total_seconds() == hours*3600


def test_midnight_clipping():
    rows = [event(start_time="2026-10-16T23:00:00-04:00", end_time="2026-10-17T01:00:00-04:00")]
    assert daily_distribution(rows, date(2026, 10, 17), "America/New_York")["planned_minutes"] == 60


@pytest.mark.asyncio
async def test_freeform_inside_window(settings, user):
    captured = []
    def handle(request):
        captured.append(request.content.decode())
        return httpx.Response(201, json={"sid": "SMsent"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await Sender(client, settings).send(user, "Hello", "reply", user.last_inbound_at+timedelta(hours=23))
    assert result == "SMsent"
    assert "Body=Hello" in captured[0]


@pytest.mark.asyncio
async def test_window_boundary_requires_template(settings, user):
    async with httpx.AsyncClient() as client:
        with pytest.raises(WindowClosed):
            await Sender(client, settings).send(user, "Hello", "reply", user.last_inbound_at+timedelta(hours=24))


@pytest.mark.asyncio
async def test_scheduled_template_outside_window(settings, user):
    settings.twilio_morning_content_sid = "HXapproved"
    captured = []
    def handle(request):
        captured.append(request.content.decode())
        return httpx.Response(201, json={"sid": "SMsent"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await Sender(client, settings).send(user, "Summary", "morning", user.last_inbound_at+timedelta(days=2))
    assert "ContentSid=HXapproved" in captured[0]
    assert "Body=" not in captured[0]


@pytest.mark.asyncio
async def test_opt_out_never_sends(settings, user):
    user.whatsapp_opt_in = False
    with pytest.raises(WindowClosed):
        await Sender(None, settings).send(user, "Hello", "reply")


@pytest.mark.asyncio
async def test_unconfigured_ai_is_honest(settings, user):
    plan = await AIBridge(None, settings).process(user, {})
    assert plan.actions == []
    assert "not connected" in plan.reply


@pytest.mark.asyncio
async def test_ambiguous_plan_does_not_execute(settings, user):
    settings.ai_base_url = "http://ai"
    from pydantic import SecretStr
    settings.ai_service_token = SecretStr("internal-token")
    calls = []
    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"actions": [event(start_time=None, end_time=None,
            status="needs_clarification", external_id=None)], "reply": "When?"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await AIBridge(client, settings).process(user, {"id": "SM1", "body": "Study", "created_at": "2026-10-17T12:00:00Z"})
    assert calls == ["/api/parse"]
    assert result.actions[0].status == "needs_clarification"


@pytest.mark.asyncio
async def test_execute_preserves_ids_and_reports_outcomes(settings, user):
    from pydantic import SecretStr
    settings.ai_base_url, settings.ai_service_token = "http://ai", SecretStr("internal-token")
    activity = event(status="proposed", external_id=None)
    def handle(request):
        assert request.headers["idempotency-key"] == "SM1"
        action = {**activity, "status": "completed", "external_id": "google-id"} if request.url.path.endswith("execute") else activity
        return httpx.Response(200, json={"actions": [action], "reply": "Something misleading"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await AIBridge(client, settings).process(user, {"id": "SM1", "body": "Study", "created_at": "2026-10-17T12:00:00Z"})
    assert result.reply == "Added: Study"
    assert result.actions[0].external_id == "google-id"


@pytest.mark.asyncio
async def test_transport_failure_never_blindly_resends(user):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=[{"id": "out1", "user_id": str(user.id), "body": "Hi", "kind": "reply"}]),
                           user=AsyncMock(return_value=user), update=AsyncMock())
    sender = SimpleNamespace(send=AsyncMock(side_effect=httpx.ReadTimeout("timeout")))
    await process_outbox(repo, sender)
    repo.update.assert_awaited_once_with("whatsapp_outbox", "out1", status="unknown", error_code="delivery_unconfirmed")
    sender.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_db_failure_after_twilio_acceptance_leaves_reconciliation_state(user):
    repo = SimpleNamespace(rpc=AsyncMock(return_value=[{"id": "out1", "user_id": str(user.id), "body": "Hi", "kind": "reply"}]),
                           user=AsyncMock(return_value=user), update=AsyncMock(side_effect=RuntimeError("db")))
    sender = SimpleNamespace(send=AsyncMock(return_value="SMsent"))
    with pytest.raises(RuntimeError):
        await process_outbox(repo, sender)
    assert repo.update.await_count == 1
    assert repo.update.call_args.kwargs["status"] == "accepted"


@pytest.mark.asyncio
async def test_inbox_persists_outcome_transactionally(user):
    message = {"id": "SM1", "user_id": str(user.id)}
    repo = SimpleNamespace(rpc=AsyncMock(side_effect=[[message], None]), user=AsyncMock(return_value=user), update=AsyncMock())
    bridge = SimpleNamespace(process=AsyncMock(return_value=Plan(actions=[Activity.model_validate(event())], reply="Added")))
    await process_inbox(repo, bridge)
    assert repo.rpc.call_args.args == ("finish_whatsapp",)
    assert repo.rpc.call_args.kwargs["p_actions"][0]["external_id"] == "google-event"


@pytest.mark.asyncio
async def test_inbox_failure_uses_atomic_reconciliation(user):
    repo = SimpleNamespace(rpc=AsyncMock(side_effect=[[{"id": "SM1", "user_id": str(user.id)}], None]),
                           user=AsyncMock(return_value=user))
    bridge = SimpleNamespace(process=AsyncMock(side_effect=httpx.ReadTimeout("uncertain Google result")))
    await process_inbox(repo, bridge)
    assert repo.rpc.call_args.args == ("fail_whatsapp",)
    assert repo.rpc.call_args.kwargs == {"p_sid": "SM1"}
    bridge.process.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_cannot_change_approved_activity(settings, user):
    from pydantic import SecretStr
    settings.ai_base_url, settings.ai_service_token = "http://ai", SecretStr("internal-token")
    activity = event(status="proposed", external_id=None)
    def handle(request):
        action = ({**activity, "title": "Unapproved", "status": "completed", "external_id": "google-id"}
                  if request.url.path.endswith("execute") else activity)
        return httpx.Response(200, json={"actions": [action], "reply": ""})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError, match="changed an approved"):
            await AIBridge(client, settings).process(user, {"id": "SM1", "body": "Study", "created_at": "2026-10-17T12:00:00Z"})


def test_recap_labels_planned_time(user):
    text = generate("evening", user, [event()], datetime(2026, 10, 18, 1, tzinfo=timezone.utc))
    assert "2.0 planned hours" in text
    assert "not measured time spent" in text


@pytest.mark.asyncio
async def test_briefing_user_timezone_and_daily_dedupe_key(user):
    user.morning_enabled = True
    repo = SimpleNamespace(rows=AsyncMock(side_effect=[[user.model_dump(mode="json")], []]),
                           activities=AsyncMock(return_value=[]), rpc=AsyncMock())
    await enqueue_briefings(repo, datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc))
    assert repo.rpc.call_args.kwargs["p_key"] == f"morning:{user.id}:2026-10-17"
    assert repo.rpc.call_args.kwargs["p_kind"] == "morning"
