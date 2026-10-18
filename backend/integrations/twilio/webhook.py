import re

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from backend.integrations.twilio.onboarding import code_hash, welcome_link

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
    # task is relied on for durability. Unlinked senders receive setup instructions
    # when a dashboard is configured; their messages never trigger scheduling.
    opt_out = form.get("OptOutType") == "STOP" or body.strip().upper() in {
        "STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"
    }
    link = re.fullmatch(r"LINK\s+([A-Za-z0-9_-]{32})", body.strip(), flags=re.IGNORECASE)
    if link and not opt_out:
        outcome = await request.app.state.repo.rpc("consume_whatsapp_link", p_hash=code_hash(link[1]), p_from=sender)
        reply = ("WhatsApp connected to Offload ✅\nWhat should I call you? Reply “Call me Ojal” using your name, or add it in the dashboard. Then send your tasks. Nothing was scheduled by linking your account."
                 if outcome == "linked" else
                 "Could not link this number. The link may have expired or an account is already linked. "
                 "Open your dashboard and select Connect WhatsApp again. Existing account links were kept.")
        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), media_type="application/xml")
    accepted = await request.app.state.repo.rpc("ingest_whatsapp", p_sid=sid, p_from=sender, p_body=body, p_opt_out=opt_out)
    if accepted is False and not opt_out and settings.dashboard_url:
        twiml = MessagingResponse()
        twiml.message(welcome_link(settings))
        return Response(str(twiml), media_type="application/xml")
    return Response("<Response></Response>", media_type="application/xml")
