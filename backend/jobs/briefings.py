from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo

from backend.db.analytics import daily_distribution, day_bounds


def generate(kind, user, rows, now):
    zone = ZoneInfo(user.timezone)
    day = now.astimezone(zone).date()
    start, end = day_bounds(day, user.timezone)
    events = sorted(
        [row for row in rows if row["type"] == "event" and row["status"] == "completed"
         and row.get("start_time") and datetime.fromisoformat(row["start_time"]) < end
         and datetime.fromisoformat(row["end_time"]) > start],
        key=lambda row: datetime.fromisoformat(row["start_time"]).astimezone(timezone.utc))
    tasks = [row for row in rows if row["type"] == "task" and row["status"] == "completed"
             and not row.get("completed_at") and row.get("due_date") and row["due_date"] <= day.isoformat()]
    summary = daily_distribution(rows, day, user.timezone)
    heading = "Good morning! Your schedule" if kind == "morning" else "Your evening recap (planned time)"
    lines = [f"{heading} for {day:%a, %b %d}:",
             f"{summary['planned_minutes']/60:.1f} planned hours · {len(events)} events · {len(tasks)} tasks due/overdue"]
    if kind == "morning":
        for event in events[:8]:
            stamp = datetime.fromisoformat(event["start_time"]).astimezone(zone)
            lines.append(f"{stamp:%I:%M %p} — {event['title']}")
        for task in tasks[:4]:
            lines.append(f"Due: {task['title']}")
        if len(events) > 8 or len(tasks) > 4:
            lines.append("See your dashboard for the full list.")
    else:
        for category in summary["categories"]:
            if category["minutes"]:
                lines.append(f"{category['category'].title()}: {category['minutes']/60:.1f}h planned")
        lines.append("This reflects your schedule, not measured time spent.")
    return "\n".join(lines)[:1500]


def generate_lineup(user, rows, now):
    zone = ZoneInfo(user.timezone)
    local = now.astimezone(zone)
    day = local.date()
    start, end = day_bounds(day, user.timezone)
    remaining_events = sorted(
        [row for row in rows if row["type"] == "event" and row["status"] == "completed"
         and row.get("start_time") and datetime.fromisoformat(row["end_time"]) > now
         and datetime.fromisoformat(row["start_time"]) < end],
        key=lambda row: datetime.fromisoformat(row["start_time"]).astimezone(timezone.utc))
    pending_tasks = [
        row for row in rows if row["type"] == "task" and row["status"] == "completed"
        and not row.get("completed_at") and row.get("due_date") and row["due_date"] <= day.isoformat()]

    lines = [f"Offload Workday Update ({local:%I:%M %p}):"]
    if remaining_events:
        lines.append(f"Upcoming commitments today ({len(remaining_events)}):")
        for ev in remaining_events[:6]:
            ev_start = datetime.fromisoformat(ev["start_time"]).astimezone(zone)
            lines.append(f"• {ev_start:%I:%M %p} — {ev['title']}")
    else:
        lines.append("No remaining meetings or calendar blocks scheduled for today.")

    if pending_tasks:
        lines.append(f"\nDeliverables due ({len(pending_tasks)}):")
        for t in pending_tasks[:4]:
            lines.append(f"• {t['title']}")

    if not remaining_events and not pending_tasks:
        lines.append("You're all clear on commitments for the rest of today! Check your Offload dashboard for upcoming client milestones.")
    elif len(remaining_events) > 6 or len(pending_tasks) > 4:
        lines.append("\nCheck your Offload dashboard for the full schedule.")

    return "\n".join(lines)[:1500]


async def enqueue_briefings(repo, now=None):
    now = now or datetime.now(timezone.utc)
    # Paginate all users; one malformed profile cannot stop other users' jobs.
    from backend.db.models import User
    offset = 0
    while True:
        users = await repo.rows("users", whatsapp_opt_in="eq.true", select="*", order="id", limit="500", offset=str(offset))
        for row in users:
            try:
                user = User.model_validate(row)
            except (ValueError, KeyError):
                logging.getLogger("timeslice.worker").error("Skipping invalid user profile: %s", row.get("id"))
                continue
            local = now.astimezone(ZoneInfo(user.timezone))
            for kind in ("morning", "evening"):
                clock = getattr(user, f"{kind}_time")[:5]
                # Exact minute prevents stale briefings after downtime. Unique key
                # prevents duplicates across worker replicas and DST fall-back.
                if getattr(user, f"{kind}_enabled") and local.strftime("%H:%M") == clock:
                    rows = await repo.activities(user.id)
                    await repo.rpc("enqueue_whatsapp", p_user_id=str(user.id),
                        p_key=f"{kind}:{user.id}:{local.date()}", p_kind=kind,
                        p_body=generate(kind, user, rows, now))

            # Periodic daytime updates every few hours (11:00, 14:00, 17:00)
            if user.morning_enabled and local.hour in (11, 14, 17) and local.minute == 0:
                if local.strftime("%H:%M") != user.morning_time[:5] and local.strftime("%H:%M") != user.evening_time[:5]:
                    rows = await repo.activities(user.id)
                    await repo.rpc("enqueue_whatsapp", p_user_id=str(user.id),
                        p_key=f"lineup:{user.id}:{local.date()}:{local.hour}", p_kind="reply",
                        p_body=generate_lineup(user, rows, now))
        if not users:
            break
        offset += len(users)

