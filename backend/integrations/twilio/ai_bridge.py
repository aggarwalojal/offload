from backend.db.models import Plan
from backend.integrations.twilio.onboarding import welcome_link


WELCOME = (
    "Welcome to TimeSlice 👋\n"
    "Your personal task and calendar assistant.\n\n"
    "Tell me what you need to get done, even if it's a messy brain dump. "
    "Include dates and times when you know them.\n\n"
    "Try: Study Java tomorrow from 7 to 9 PM, and remind me to apply for an internship Friday."
)
SETUP_PENDING = "Scheduling is not connected yet, so nothing was scheduled."


def is_greeting(body: str) -> bool:
    # Only a whole-message greeting is handled locally. A task containing "hi"
    # or "help" must still reach the AI rather than being silently discarded.
    normalized = " ".join(body.casefold().split()).strip(" !.,?👋")
    return normalized in {"hi", "hello", "hey", "hi timeslice", "hello timeslice",
                          "hey timeslice", "start", "help", "menu"}


def read_plan(payload: dict, key: str) -> Plan:
    """Map Jia's current response to Eva's validated model at this boundary.

    Parser metadata is not an approved Google action. Event durations continue
    to come from the validated timestamps, never an independent duration field.
    """
    actions = []
    for item in payload[key]:
        action = dict(item)
        action.pop("duration_minutes", None)
        action.pop("clarification_needed", None)
        actions.append(action)
    return Plan.model_validate({"actions": actions, "reply": payload.get("whatsapp_reply", "")})


class AIBridge:
    """Replaceable adapter; this module does not implement Gemini or Google APIs."""

    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    async def process(self, user, message: dict) -> Plan:
        if is_greeting(message.get("body", "")):
            if self.settings.dashboard_url:
                return Plan(reply=welcome_link(self.settings, linked=True))
            suffix = "What would you like to plan?" if self.settings.ai_base_url else SETUP_PENDING
            return Plan(reply=f"{WELCOME}\n\n{suffix}")
        if not self.settings.ai_base_url:
            if self.settings.dashboard_url:
                return Plan(reply=f"{welcome_link(self.settings, linked=True)}\n\n{SETUP_PENDING}")
            return Plan(reply=f"{WELCOME}\n\n{SETUP_PENDING}")
        if not self.settings.ai_service_token.get_secret_value():
            raise RuntimeError("AI_SERVICE_TOKEN is required for internal API calls")
        if not message["body"].strip():
            return Plan(reply="Please send your tasks or plans as text. I cannot process attachments yet.")
        context = {"user_id": str(user.id), "message_id": message["id"], "timezone": user.timezone,
                   "reference_time": message["created_at"], "message": message["body"]}
        headers = {"Authorization": f"Bearer {self.settings.ai_service_token.get_secret_value()}",
                   "Idempotency-Key": message["id"]}
        parsed = await self.client.post(f"{self.settings.ai_base_url.rstrip('/')}/api/parse",
                                        json={**context, "current_time": message["created_at"]}, headers=headers, timeout=45)
        parsed.raise_for_status()
        payload = parsed.json()
        activities_contract = "activities" in payload and "actions" not in payload
        plan = read_plan(payload, "activities") if activities_contract else Plan.model_validate(payload)
        if activities_contract and payload.get("needs_clarification"):
            for action in plan.actions:
                action.status = "needs_clarification"
                action.external_id = None
            plan.reply = payload.get("clarification_prompt") or plan.reply
        # Clarifications do not trigger partial execution or invented default times.
        if not plan.actions or any(not action.ready_to_create() for action in plan.actions):
            for action in plan.actions:
                # Never persist an unexecuted parser claim as a successful Google sync.
                action.status = "needs_clarification"
                action.external_id = None
            plan.reply = "Nothing was scheduled. " + (plan.reply or "Please clarify the date, start time and duration of your events.")
            return plan
        execution_base = self.settings.google_execution_url or self.settings.ai_base_url
        executed = await self.client.post(f"{execution_base.rstrip('/')}/api/execute",
            json={**context, "activities" if activities_contract else "actions": [a.model_dump(mode="json") for a in plan.actions],
                  "authorization_source": "inbound_whatsapp_create_request"}, headers=headers, timeout=60)
        executed.raise_for_status()
        payload = executed.json()
        result = read_plan(payload, "results") if activities_contract else Plan.model_validate(payload)
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
