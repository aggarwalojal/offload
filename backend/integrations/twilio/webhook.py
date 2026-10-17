import re

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

router = APIRouter()


@router.post("/api/whatsapp")
async def incoming(request: Request):
    settings = request.app.state.settings
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected a Twilio form")
    # Validate ALL fields and the configured public URL, never forwarded Host headers.
    form = await request.form(max_fields=100)
    if not RequestValidator(settings.twilio_auth_token.get_secret_value()).validate(
        settings.twilio_webhook_url, form, request.headers.get("x-twilio-signature", "")
    ):
        raise HTTPException(403, "Invalid Twilio signature")
    if form.get("AccountSid") != settings.twilio_account_sid or form.get("To") != settings.twilio_whatsapp_from:
        raise HTTPException(403, "Unexpected Twilio account or destination")
    sid, sender, body = form.get("MessageSid", ""), form.get("From", ""), form.get("Body", "")
    if not re.fullmatch(r"SM[0-9a-fA-F]{32}", sid) or not re.fullmatch(r"whatsapp:\+[1-9][0-9]{6,14}", sender):
        raise HTTPException(422, "Invalid message identifiers")
    if len(body) > 10000:
        raise HTTPException(413, "Message too long")
    # A DB failure returns 503 via the app handler so Twilio may retry. No background
    # task is relied on for durability. Unlinked/non-opted-in senders are ignored.
    opt_out = form.get("OptOutType") == "STOP" or body.strip().upper() in {
        "STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"
    }
    await request.app.state.repo.rpc("ingest_whatsapp", p_sid=sid, p_from=sender, p_body=body, p_opt_out=opt_out)
    return Response("<Response></Response>", media_type="application/xml")
