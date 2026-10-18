"""Bind a verified Supabase login to a signed inbound WhatsApp sender."""
from hashlib import sha256
import secrets
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

router = APIRouter()


def code_hash(code: str) -> str:
    return sha256(code.encode()).hexdigest()


def dashboard_link(settings) -> str:
    return f"{settings.dashboard_url}/?view=settings" if settings.dashboard_url else ""


def welcome_link(settings, *, linked: bool = False, display_name: str | None = None) -> str:
    instructions = ("Your WhatsApp is linked. Connect Google Calendar and Google Tasks in the dashboard if you haven't already, "
                    "then return here and send your tasks." if linked else
                    "Then select Connect WhatsApp and send its verification message here. "
                    "Return to this chat to send your tasks.")
    greeting = f"Hey, {display_name}! 👋" if display_name else "Welcome to Offload 👋"
    name_prompt = "" if display_name else "What should I call you? Add your name in the dashboard, or once WhatsApp is linked reply “Call me Ojal” using your name.\n\n"
    return (f"{greeting}\nYour personal task and calendar assistant.\n\n{name_prompt}"
            f"Open your dashboard to connect Google Calendar and Google Tasks:\n{dashboard_link(settings)}\n\n"
            f"{instructions}\nNothing has been scheduled by this welcome message.")


async def verified_identity(request: Request) -> UUID:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to Offload first")
    settings = request.app.state.settings
    response = await request.app.state.client.get(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
        headers={"apikey": settings.supabase_service_role_key.get_secret_value(),
                 "Authorization": authorization},
    )
    if response.status_code in {401, 403}:
        raise HTTPException(401, "Sign in to Offload again")
    response.raise_for_status()
    try:
        identity = response.json()
        if not identity.get("email_confirmed_at"):
            raise ValueError("Email must be verified")
        return UUID(identity["id"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(403, "A verified account is required") from None


class LinkRequest(BaseModel):
    timezone: str = "America/New_York"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Choose a valid timezone") from None
        return value


@router.get("/api/whatsapp/link")
async def link_status(request: Request, user_id=Depends(verified_identity)):
    rows = await request.app.state.repo.rows("users", id=f"eq.{user_id}", select="whatsapp_opt_in")
    return {"connected": bool(rows and rows[0]["whatsapp_opt_in"])}


@router.post("/api/whatsapp/link")
async def issue_link(body: LinkRequest, request: Request, user_id=Depends(verified_identity)):
    code = secrets.token_urlsafe(24)
    await request.app.state.repo.rpc("issue_whatsapp_link", p_user_id=str(user_id),
                                    p_hash=code_hash(code), p_timezone=body.timezone)
    number = request.app.state.settings.twilio_whatsapp_from.removeprefix("whatsapp:+")
    return {"url": f"https://wa.me/{number}?text=LINK%20{code}", "expires_in": 900}
