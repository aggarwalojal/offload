"""Test-only provider simulator. SQL uses the real migration/functions.

This small PostgREST stand-in does not test the hosted Supabase HTTP service.
No production route, repository or worker is replaced.
"""
import json
import re
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import httpx

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "22222222-2222-2222-2222-222222222222"


def literal(value):
    if value is None: return "null"
    if isinstance(value, bool): return "true" if value else "false"
    if isinstance(value, (list, dict)): value = json.dumps(value)
    return "'"+str(value).replace("'", "''")+"'"


class Gateway:
    tables = {"users", "time_entries", "tasks", "agent_actions", "whatsapp_inbox", "whatsapp_outbox"}
    functions = {"ingest_whatsapp", "claim_whatsapp_inbox", "claim_whatsapp_outbox", "finish_whatsapp", "fail_whatsapp", "enqueue_whatsapp"}

    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.mode = "success"
        self.calls, self.sent, self.history = [], [], []

    def rows(self, table):
        assert table in self.tables
        return self.db.json(f"select coalesce(jsonb_agg(to_jsonb(t)),'[]') from public.{table} t")

    def activities(self, sid):
        day = datetime.now(ZoneInfo("America/New_York")).date()
        start = datetime.combine(day, datetime.min.time(), ZoneInfo("America/New_York"))+timedelta(hours=10)
        return [{"id": str(uuid5(NAMESPACE_URL,sid+kind)), "type":kind, "title": "Study Java" if kind=="event" else "Apply for internship",
                 "category":"academics" if kind=="event" else "career", "start_time":start.isoformat() if kind=="event" else None,
                 "end_time":(start+timedelta(hours=2)).isoformat() if kind=="event" else None,
                 "due_date":None if kind=="event" else day.isoformat(), "status":"proposed", "external_id":None, "source":"whatsapp"}
                for kind in ("event","task")]

    def handle(self, request):
        self.calls.append((request.url.host, request.url.path))
        if request.url.host == "example.supabase.co":
            assert request.headers["apikey"] == self.settings.supabase_service_role_key.get_secret_value()
            if request.url.path == "/auth/v1/user":
                token = request.headers.get("authorization")
                if token not in {"Bearer user-one", "Bearer user-two"}:
                    return httpx.Response(401,json={})
                return httpx.Response(200,json={"id":USER_ID if token.endswith("one") else OTHER_ID})
            assert request.headers["authorization"] == "Bearer "+self.settings.supabase_service_role_key.get_secret_value()
            if "/rpc/" in request.url.path:
                name = request.url.path.rsplit("/",1)[1]
                assert name in self.functions
                data = json.loads(request.content)
                assert all(re.fullmatch(r"p_[a-z_]+", key) for key in data)
                args = ",".join(f"{key} => {literal(value)}" for key,value in data.items())
                call = f"public.{name}({args})"
                if name.startswith("claim_"):
                    result = self.db.json(f"set role service_role; select coalesce(jsonb_agg(to_jsonb(t)),'[]') from {call} t")
                elif name == "ingest_whatsapp":
                    result = self.db.json(f"set role service_role; select to_jsonb({call})")
                else:
                    self.db.sql(f"set role service_role; select {call}")
                    result = None
                return httpx.Response(200,json=result)
            table = request.url.path.rsplit("/",1)[1]
            assert table in self.tables
            conditions = []
            for key,value in request.url.params.items():
                if key in {"id","user_id","whatsapp_opt_in","status"}:
                    assert value.startswith("eq.")
                    conditions.append(f"{key}={literal(value[3:])}")
            where = " where "+" and ".join(conditions) if conditions else ""
            if request.method == "PATCH":
                values = json.loads(request.content)
                assert all(key in {"status","error_code","twilio_sid","created_at"} for key in values)
                assignments = ",".join(f"{key}={literal(value)}" for key,value in values.items())
                self.db.sql(f"set role service_role; update public.{table} set {assignments}{where}")
                return httpx.Response(204)
            order = request.url.params.get("order","id").replace(".desc"," desc")
            assert order in {"id","created_at desc"}
            limit,offset = int(request.url.params.get("limit",1000)),int(request.url.params.get("offset",0))
            result = self.db.json(f"set role service_role; select coalesce(jsonb_agg(to_jsonb(t)),'[]') from (select * from public.{table}{where} order by {order} limit {limit} offset {offset}) t")
            return httpx.Response(200,json=result)
        if request.url.host == "ai.test":
            assert request.headers["authorization"] == "Bearer test-internal"
            data = json.loads(request.content)
            assert data["user_id"] == USER_ID
            assert request.headers["idempotency-key"] == data["message_id"]
            if self.mode == "timeout": raise httpx.ReadTimeout("simulated timeout",request=request)
            if self.mode == "malformed": return httpx.Response(200,json={"actions":[{"title":"invalid"}]})
            if request.url.path.endswith("parse"):
                actions = self.activities(data["message_id"])
                if self.mode == "ambiguous":
                    actions[0].update(start_time=None,end_time=None,status="needs_clarification")
                return httpx.Response(200,json={"actions":actions,"reply":"What time?" if self.mode == "ambiguous" else ""})
            actions = data["actions"]
            for action in actions:
                failed = self.mode == "partial" and action["type"] == "task"
                action.update(status="failed" if failed else "completed",external_id=None if failed else "google-"+action["id"])
            return httpx.Response(200,json={"actions":actions,"reply":"untrusted provider prose"})
        if request.url.host == "api.twilio.com":
            assert request.headers["authorization"].startswith("Basic ")
            if request.method == "GET":
                return httpx.Response(200,json={"messages":self.history,"next_page_uri":None})
            self.sent.append(httpx.QueryParams(request.content.decode()))
            return httpx.Response(201,json={"sid":"SM"+f"{len(self.sent):032x}"})
        raise AssertionError(f"Unexpected external request: {request.url.host}")
