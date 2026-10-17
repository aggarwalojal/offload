"""Run separately: python -m backend.jobs.worker. No scheduler in web workers."""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

from backend.db.repository import Repository
from backend.integrations.twilio.ai_bridge import AIBridge
from backend.integrations.twilio.config import Settings
from backend.integrations.twilio.sender import Sender, WindowClosed
from backend.jobs.briefings import enqueue_briefings

log = logging.getLogger("timeslice.worker")


async def process_inbox(repo, bridge):
    messages = await repo.rpc("claim_whatsapp_inbox")
    for message in messages:
        try:
            user = await repo.user(message["user_id"])
            if not user.whatsapp_opt_in:
                await repo.update("whatsapp_inbox", message["id"], status="failed", error_code="opt_out")
                continue
            plan = await bridge.process(user, message)
            await repo.rpc("finish_whatsapp", p_sid=message["id"],
                p_actions=[a.model_dump(mode="json") for a in plan.actions],
                p_reply=plan.reply or "No activities were scheduled. Please send a task or event to add.")
        except Exception:
            # Exceptions may contain authorization headers/message content: log IDs only.
            log.error("Inbox requires reconciliation: %s", message["id"])
            await repo.rpc("fail_whatsapp", p_sid=message["id"])


async def process_outbox(repo, sender):
    messages = await repo.rpc("claim_whatsapp_outbox")
    for message in messages:
        try:
            user = await repo.user(message["user_id"])
            sid = await sender.send(user, message["body"], message["kind"])
        except WindowClosed as exc:
            await repo.update("whatsapp_outbox", message["id"], status="blocked", error_code=str(exc))
        except httpx.HTTPStatusError as exc:
            # 5xx may be ambiguous; do not automatically send duplicate messages.
            status = "unknown" if exc.response.status_code >= 500 else "failed"
            await repo.update("whatsapp_outbox", message["id"], status=status,
                              error_code=f"twilio_http_{exc.response.status_code}")
        except Exception:
            await repo.update("whatsapp_outbox", message["id"], status="unknown", error_code="delivery_unconfirmed")
        else:
            # Keep this outside the send try block: a DB failure after acceptance
            # must leave 'sending' for reconciliation, never cause a resend.
            await repo.update("whatsapp_outbox", message["id"], status="accepted", twilio_sid=sid)


async def run():
    settings = Settings()
    async with httpx.AsyncClient(timeout=15) as client:
        repo = Repository(client, settings.supabase_url, settings.supabase_service_role_key.get_secret_value())
        bridge, sender = AIBridge(client, settings), Sender(client, settings)
        async def poll(operation):
            while True:
                try:
                    await operation()
                except Exception:
                    log.error("Worker cycle failed; inspect queue states and service configuration")
                await asyncio.sleep(settings.worker_poll_seconds)

        # Scheduling and outbound replies keep running during slow AI calls.
        await asyncio.gather(
            poll(lambda: enqueue_briefings(repo)),
            poll(lambda: process_inbox(repo, bridge)),
            poll(lambda: process_outbox(repo, sender)),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
