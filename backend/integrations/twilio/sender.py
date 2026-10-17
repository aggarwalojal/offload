import json
from datetime import datetime, timedelta, timezone

import httpx


class WindowClosed(Exception):
    pass


class Sender:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    async def send(self, user, body: str, kind: str, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        if not user.whatsapp_opt_in:
            raise WindowClosed("opt_out")
        data = {"From": self.settings.twilio_whatsapp_from, "To": user.whatsapp_number}
        if user.last_inbound_at and timedelta(0) <= now-user.last_inbound_at < timedelta(hours=24):
            data["Body"] = body[:1500]
        else:
            content_sid = {"morning": self.settings.twilio_morning_content_sid,
                           "evening": self.settings.twilio_evening_content_sid}.get(kind)
            if not content_sid:
                raise WindowClosed("template_required")
            data.update(ContentSid=content_sid, ContentVariables=json.dumps({"1": body[:1000]}))
        response = await self.client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_account_sid}/Messages.json",
            data=data, auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token.get_secret_value()),
        )
        response.raise_for_status()
        return response.json()["sid"]
