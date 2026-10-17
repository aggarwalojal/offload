from datetime import datetime, timezone

from backend.db.models import Plan


class AIBridge:
    """Replaceable adapter; this module does not implement Gemini or Google APIs."""

    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    async def process(self, user, message: dict) -> Plan:
        if not self.settings.ai_base_url:
            return Plan(reply="TimeSlice's AI service is not connected yet. Nothing was scheduled. Please try again once it is connected.")
        if not self.settings.ai_service_token.get_secret_value():
            raise RuntimeError("AI_SERVICE_TOKEN is required for internal API calls")
        if not message["body"].strip():
            return Plan(reply="Please send your tasks or plans as text. I cannot process attachments yet.")
        context = {"user_id": str(user.id), "message_id": message["id"], "timezone": user.timezone,
                   "reference_time": message["created_at"], "message": message["body"]}
        headers = {"Authorization": f"Bearer {self.settings.ai_service_token.get_secret_value()}",
                   "Idempotency-Key": message["id"]}
        parsed = await self.client.post(f"{self.settings.ai_base_url.rstrip('/')}/api/parse",
                                        json=context, headers=headers, timeout=45)
        parsed.raise_for_status()
        plan = Plan.model_validate(parsed.json())
        # Clarifications do not trigger partial execution or invented default times.
        if not plan.actions or any(not action.ready_to_create() for action in plan.actions):
            for action in plan.actions:
                # Never persist an unexecuted parser claim as a successful Google sync.
                action.status = "needs_clarification"
                action.external_id = None
            plan.reply = "Nothing was scheduled. " + (plan.reply or "Please clarify the date, start time and duration of your events.")
            return plan
        executed = await self.client.post(f"{self.settings.ai_base_url.rstrip('/')}/api/execute",
            json={**context, "actions": [a.model_dump(mode="json") for a in plan.actions],
                  "authorization_source": "inbound_whatsapp_create_request"}, headers=headers, timeout=60)
        executed.raise_for_status()
        result = Plan.model_validate(executed.json())
        expected = {a.id: a for a in plan.actions}
        if {a.id for a in result.actions} != set(expected):
            raise ValueError("Execution results must match every proposed action ID")
        for action in result.actions:
            original = expected[action.id]
            if action.model_dump(exclude={"status", "external_id"}) != original.model_dump(exclude={"status", "external_id"}):
                raise ValueError("Execution changed an approved activity")
            if action.status not in {"completed", "failed", "needs_clarification"}:
                raise ValueError("Execution must return terminal outcomes or clarification")
        # Confirmation comes from validated outcomes, not an untrusted prose claim.
        result.reply = "\n".join(
            f"{'Added' if a.status == 'completed' else 'Needs clarification' if a.status == 'needs_clarification' else 'Could not add'}: {a.title}"
            for a in result.actions
        )[:1500]
        return result
