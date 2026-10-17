from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from backend.db.analytics import daily_distribution

router = APIRouter()


async def current_user(request: Request):
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "A Supabase user access token is required")
    settings = request.app.state.settings
    response = await request.app.state.client.get(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
        headers={"apikey": settings.supabase_service_role_key.get_secret_value(),
                 "Authorization": authorization},
    )
    if response.status_code in (401, 403):
        raise HTTPException(401, "Invalid or expired user token")
    response.raise_for_status()
    try:
        user_id = UUID(response.json()["id"])
        return await request.app.state.repo.user(user_id)
    except (KeyError, ValueError):
        raise HTTPException(403, "Link your TimeSlice account first") from None


@router.get("/api/activities")
async def activities(request: Request, user=Depends(current_user)):
    return {"activities": await request.app.state.repo.activities(user.id)}


@router.get("/api/analytics/today")
async def today(request: Request, user=Depends(current_user)):
    rows = await request.app.state.repo.activities(user.id)
    return daily_distribution(rows, datetime.now(ZoneInfo(user.timezone)).date(), user.timezone)


@router.get("/api/analytics/week")
async def week(request: Request, user=Depends(current_user)):
    rows = await request.app.state.repo.activities(user.id)
    day = datetime.now(ZoneInfo(user.timezone)).date()
    monday = day - timedelta(days=day.weekday())
    return {"days": [daily_distribution(rows, monday+timedelta(days=i), user.timezone) for i in range(7)]}


@router.get("/api/agent-actions")
async def actions(request: Request, user=Depends(current_user)):
    return {"actions": await request.app.state.repo.rows(
        "agent_actions", user_id=f"eq.{user.id}", order="created_at.desc", limit="100", select="*")}
