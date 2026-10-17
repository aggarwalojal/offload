"""Hackathon-only inbound transport using Twilio's authenticated message history.

Run: python -m backend.integrations.twilio.demo_poll
This polls real messages; it is not a webhook or a simulated WhatsApp integration.
Replies are deliberately blocked unless --send-replies is explicitly selected for
a sender/account that supports the app's free-form Messaging API replies.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import ValidationError

from backend.db.repository import Repository
from backend.integrations.twilio.ai_bridge import AIBridge
from backend.integrations.twilio.config import Settings
from backend.integrations.twilio.sender import Sender, WindowClosed
from backend.jobs.worker import process_inbox, process_outbox

log = logging.getLogger("timeslice.demo")


class NoDemoReplies:
    async def send(self, user, body, kind):
        raise WindowClosed("demo_replies_disabled")


class InboundPoller:
    def __init__(self, client, repo, settings, since):
        self.client, self.repo, self.settings, self.since = client, repo, settings, since
        self.path = f"/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
        self.seen = set()

    async def poll_once(self):
        url = "https://api.twilio.com"+self.path
        params = {"To":self.settings.twilio_whatsapp_from,"PageSize":"1000",
                  "DateSent>":(self.since-timedelta(days=1)).strftime("%Y-%m-%d")}
        messages = []
        # Bounded demo traffic, with explicit failure rather than silent truncation.
        for _ in range(20):
            response = await self.client.get(url,params=params,
                auth=(self.settings.twilio_account_sid,self.settings.twilio_auth_token.get_secret_value()))
            response.raise_for_status()
            page = response.json()
            reached_start = False
            for row in page["messages"]:
                stamp = parsedate_to_datetime(row["date_created"])
                if stamp.tzinfo is None:
                    raise ValueError("Twilio message timestamp has no timezone")
                if stamp < self.since:
                    reached_start = True
                    continue
                if (row.get("direction") != "inbound" or row.get("account_sid") != self.settings.twilio_account_sid
                    or row.get("to") != self.settings.twilio_whatsapp_from):
                    continue
                sid, sender, body = row.get("sid",""),row.get("from",""),row.get("body") or ""
                if sid in self.seen:
                    continue
                if not re.fullmatch(r"SM[0-9a-fA-F]{32}",sid) or not re.fullmatch(r"whatsapp:\+[1-9][0-9]{6,14}",sender):
                    continue
                if len(body) > 10000:
                    log.warning("Skipping oversized message: %s",sid)
                    continue
                messages.append((stamp,sid,sender,body))
            next_uri = page.get("next_page_uri")
            if not next_uri or reached_start:
                break
            url = urljoin("https://api.twilio.com",next_uri)
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc != "api.twilio.com" or parsed.path != self.path:
                raise ValueError("Unexpected Twilio pagination URL")
            params = None
        else:
            raise RuntimeError("Demo history exceeds 20 pages; narrow the time window")
        for stamp,sid,sender,body in sorted(messages):
            accepted = await self.repo.rpc("ingest_whatsapp",p_sid=sid,p_from=sender,p_body=body,
                p_opt_out=body.strip().upper() in {"STOP","STOPALL","UNSUBSCRIBE","CANCEL","END","QUIT"})
            if accepted:
                # Preserve relative-date context. Replayed SIDs are already deduped
                # by Postgres and processed rows are never modified.
                await self.repo.request("PATCH","whatsapp_inbox",
                    params={"id":f"eq.{sid}","status":"eq.pending"},json={"created_at":stamp.isoformat()})
            # Mark only after all persistence requests finish. A failed DB call
            # can be retried, while an old STOP isn't replayed every five seconds.
            self.seen.add(sid)
        return len(messages)


async def check_access(client, repo, settings):
    """Read-only credential check: no ingestion, AI calls or outgoing messages."""
    response = await client.get(
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
        params={"To":settings.twilio_whatsapp_from,"PageSize":"1"},
        auth=(settings.twilio_account_sid,settings.twilio_auth_token.get_secret_value()))
    response.raise_for_status()
    messages = response.json()["messages"]
    users = await repo.rows("users",select="id",limit="1")
    log.info("Twilio Messages API: accessible; matching recent message found: %s",bool(messages))
    log.info("Supabase users table: accessible; linked user found: %s",bool(users))
    if not messages:
        log.warning("No message found for this sender. API access alone doesn't establish that trial inbound messages are exposed.")


async def run(send_replies=False, check_only=False):
    settings = Settings()
    if not re.fullmatch(r"AC[0-9a-fA-F]{32}",settings.twilio_account_sid):
        raise ValueError("Set TWILIO_ACCOUNT_SID to your real Account SID in backend/.env")
    # Only messages received after launch are ingested. No old task requests are
    # unexpectedly replayed when starting the demo.
    since = datetime.now(timezone.utc).replace(microsecond=0)
    async with httpx.AsyncClient(timeout=15) as client:
        repo = Repository(client,settings.supabase_url,settings.supabase_service_role_key.get_secret_value())
        if check_only:
            await check_access(client,repo,settings)
            return
        poller = InboundPoller(client,repo,settings,since)
        bridge = AIBridge(client,settings)
        sender = Sender(client,settings) if send_replies else NoDemoReplies()
        log.info("DEMO: polling Twilio message history every 5 seconds. Send a NEW message now.")
        log.info("Custom outbound replies: %s", "enabled" if send_replies else "disabled; Twilio may still send its standard auto-reply")
        while True:
            try:
                count = await poller.poll_once()
                if count:
                    log.info("Read %s matching message(s); Postgres deduplicates MessageSids",count)
                await process_inbox(repo,bridge)
                await process_outbox(repo,sender)
            except httpx.HTTPStatusError as exc:
                # Do not log provider bodies or headers containing credentials/PII.
                log.error("Provider HTTP %s; check credentials, API access and sender",exc.response.status_code)
                if exc.response.status_code in {401,403}:
                    return
            except Exception as exc:
                log.error("Demo cycle failed (%s); inspect configuration and queue states",type(exc).__name__)
            await asyncio.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send-replies",action="store_true",help="Only for accounts/senders supporting custom free-form API replies")
    parser.add_argument("--check",action="store_true",help="Check real Twilio/Supabase read access and exit without processing or sending")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run(args.send_replies,args.check))
    except KeyboardInterrupt:
        pass
    except ValidationError as exc:
        # Pydantic's default exception display can contain configuration values.
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
        log.error("Fill or correct these settings in backend/.env: %s",fields)
        raise SystemExit(1)
    except httpx.HTTPStatusError as exc:
        log.error("Provider HTTP %s; check credentials and sender/API access",exc.response.status_code)
        raise SystemExit(1)
    except (ValueError,httpx.RequestError) as exc:
        log.error("Setup check failed (%s); verify settings and network access",type(exc).__name__)
        raise SystemExit(1)
