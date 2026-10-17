"""Real webhook, bridge, repo, workers and routers; fake provider HTTP, real SQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from backend.db.repository import Repository
from backend.integrations.twilio.ai_bridge import AIBridge
from backend.integrations.twilio.app import create_app
from backend.integrations.twilio.sender import Sender
from backend.jobs.briefings import enqueue_briefings
from backend.jobs.worker import process_inbox, process_outbox
from backend.tests.component_gateway import Gateway, OTHER_ID, USER_ID
from backend.tests.test_whatsapp import settings, signed_form


@pytest.fixture
async def component(postgres,settings):
    postgres.sql(f"""truncate auth.users cascade;
      insert into auth.users(id) values ('{USER_ID}'),('{OTHER_ID}');
      insert into public.users(id,whatsapp_number,whatsapp_opt_in) values
      ('{USER_ID}','whatsapp:+15551234567',true),('{OTHER_ID}','whatsapp:+15557654321',true);""")
    settings.ai_base_url,settings.ai_service_token = "https://ai.test",SecretStr("test-internal")
    gateway = Gateway(postgres,settings)
    async with httpx.AsyncClient(transport=httpx.MockTransport(gateway.handle)) as upstream:
        repo = Repository(upstream,settings.supabase_url,settings.supabase_service_role_key.get_secret_value())
        app = create_app(settings,repo,upstream)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url="http://component.test") as api:
                yield SimpleNamespace(db=postgres,repo=repo,api=api,gateway=gateway,settings=settings,
                    bridge=AIBridge(upstream,settings),sender=Sender(upstream,settings))


async def incoming(component,**overrides):
    form,headers = signed_form(component.settings,**overrides)
    response = await component.api.post("/api/whatsapp",data=form,headers=headers)
    assert response.status_code == 200,response.text


@pytest.mark.parametrize("mode",["success","partial","ambiguous","timeout","malformed","unconfigured"])
async def test_complete_local_flow(component,mode):
    c = component
    c.gateway.mode = mode
    if mode == "unconfigured": c.settings.ai_base_url = ""
    await incoming(c)
    await incoming(c)  # Twilio retry must not duplicate the message or the work.
    assert len(c.gateway.rows("whatsapp_inbox")) == 1
    await process_inbox(c.repo,c.bridge)
    await process_inbox(c.repo,c.bridge)
    await process_outbox(c.repo,c.sender)
    await process_outbox(c.repo,c.sender)
    assert len(c.gateway.sent) == 1
    inbox = c.gateway.rows("whatsapp_inbox")[0]
    outbox = c.gateway.rows("whatsapp_outbox")[0]
    assert outbox["status"] == "accepted" and outbox["twilio_sid"]
    headers = {"Authorization":"Bearer user-one"}
    activities = (await c.api.get("/api/activities",headers=headers)).json()["activities"]
    feed = (await c.api.get("/api/agent-actions",headers=headers)).json()["actions"]
    today = (await c.api.get("/api/analytics/today",headers=headers)).json()
    week = (await c.api.get("/api/analytics/week",headers=headers)).json()["days"]
    assert len(week) == 7
    if mode in {"success","partial"}:
        assert inbox["status"] == "completed" and len(activities) == len(feed) == 2
        assert today["planned_minutes"] == 120
        assert sum(day["planned_minutes"] for day in week) == 120
        assert "Added: Study Java" in c.gateway.sent[0]["Body"]
        assert ("Could not add: Apply" in c.gateway.sent[0]["Body"]) == (mode == "partial")
    elif mode == "ambiguous":
        assert len(activities) == 2 and all(a["status"] == "needs_clarification" for a in activities)
        assert today["planned_minutes"] == 0
        assert not any(path == "/api/execute" for host,path in c.gateway.calls)
    else:
        assert not activities and not feed
        assert inbox["status"] == ("completed" if mode == "unconfigured" else "failed")
        assert today["planned_minutes"] == 0
    for route,key in [("/api/activities","activities"),("/api/agent-actions","actions")]:
        response = await c.api.get(route,headers={"Authorization":"Bearer user-two"})
        assert response.status_code == 200 and response.json()[key] == []


async def test_stop_blocks_already_queued_work_and_unknown_sender_is_ignored(component):
    c = component
    await incoming(c,From="whatsapp:+15550009999")
    assert c.gateway.rows("whatsapp_inbox") == []
    await incoming(c)
    await incoming(c,MessageSid="SM"+"c"*32,Body="STOP")
    await process_inbox(c.repo,c.bridge)
    assert c.gateway.rows("whatsapp_inbox")[0]["error_code"] == "opt_out"
    assert not c.gateway.rows("time_entries") and not c.gateway.sent
    assert not any(host == "ai.test" for host,path in c.gateway.calls)


@pytest.mark.parametrize("kind",["morning","evening"])
async def test_scheduled_flow_deduplicates_and_honors_window(component,kind):
    c = component
    now = datetime.now(timezone.utc)
    c.db.sql(f"update public.users set timezone='UTC',{kind}_enabled=true,{kind}_time='{now:%H:%M}' where id='{USER_ID}'")
    await enqueue_briefings(c.repo,now)
    await enqueue_briefings(c.repo,now)
    assert len(c.gateway.rows("whatsapp_outbox")) == 1
    await process_outbox(c.repo,c.sender)
    row = c.gateway.rows("whatsapp_outbox")[0]
    assert row["status"] == "blocked" and row["error_code"] == "template_required"
    assert not c.gateway.sent
    setattr(c.settings,f"twilio_{kind}_content_sid","HXtest-template")
    c.db.sql(f"update public.whatsapp_outbox set status='pending' where id='{row['id']}'")
    await process_outbox(c.repo,c.sender)
    assert c.gateway.rows("whatsapp_outbox")[0]["status"] == "accepted"
    assert c.gateway.sent[0]["ContentSid"] == "HXtest-template"
    assert "Body" not in c.gateway.sent[0]


async def test_concurrent_workers_claim_each_message_once(component):
    c = component
    for number in range(12):
        await incoming(c,MessageSid="SM"+f"{number:032x}")
    def claim(_):
        return c.db.json("set role service_role; select coalesce(jsonb_agg(to_jsonb(t)),'[]') from public.claim_whatsapp_inbox() t")
    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(claim,range(20)))
    ids = [row["id"] for batch in batches for row in batch]
    assert len(ids) == len(set(ids)) == 12


async def test_fall_back_repeated_local_minute_enqueues_once(component):
    c = component
    c.db.sql(f"update public.users set morning_enabled=true,morning_time='01:30' where id='{USER_ID}'")
    await enqueue_briefings(c.repo,datetime(2026,11,1,5,30,tzinfo=timezone.utc))
    await enqueue_briefings(c.repo,datetime(2026,11,1,6,30,tzinfo=timezone.utc))
    assert len(c.gateway.rows("whatsapp_outbox")) == 1
    assert c.gateway.rows("whatsapp_outbox")[0]["dedupe_key"] == f"morning:{USER_ID}:2026-11-01"


async def test_demo_poll_to_real_database_and_existing_worker(component):
    from email.utils import format_datetime
    from backend.integrations.twilio.demo_poll import InboundPoller, NoDemoReplies
    c = component
    now = datetime.now(timezone.utc).replace(microsecond=0)
    c.gateway.history = [{"sid":"SM"+"d"*32,"account_sid":c.settings.twilio_account_sid,
        "direction":"inbound","to":c.settings.twilio_whatsapp_from,"from":"whatsapp:+15551234567",
        "body":"Study Java 10 AM to noon","date_created":format_datetime(now)}]
    poller = InboundPoller(c.bridge.client,c.repo,c.settings,now)
    await poller.poll_once()
    await poller.poll_once()
    await process_inbox(c.repo,c.bridge)
    await process_outbox(c.repo,NoDemoReplies())
    await poller.poll_once()
    await process_inbox(c.repo,c.bridge)
    assert len(c.gateway.rows("whatsapp_inbox")) == 1
    assert c.gateway.rows("whatsapp_inbox")[0]["status"] == "completed"
    assert len(c.gateway.rows("time_entries")) == len(c.gateway.rows("tasks")) == 1
    assert len(c.gateway.rows("agent_actions")) == 2
    assert c.gateway.rows("whatsapp_outbox")[0]["error_code"] == "demo_replies_disabled"
    assert not c.gateway.sent
