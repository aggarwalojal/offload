from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.db.models import Category


def day_bounds(day: date, tz: str):
    zone = ZoneInfo(tz)
    return (datetime.combine(day, time(), zone).astimezone(timezone.utc),
            datetime.combine(day + timedelta(days=1), time(), zone).astimezone(timezone.utc))


def daily_distribution(activities: list[dict], day: date, tz: str) -> dict:
    """Union of scheduled intervals; split overlapping time equally by category.

    All arithmetic is UTC so DST days are correctly 23/25 hours. Task sync and
    actual time spent are deliberately excluded from planned event minutes.
    """
    start, end = day_bounds(day, tz)
    events = []
    for row in activities:
        if row["type"] != "event" or row["status"] != "completed" or not row.get("start_time"):
            continue
        left = max(start, datetime.fromisoformat(row["start_time"]).astimezone(timezone.utc))
        right = min(end, datetime.fromisoformat(row["end_time"]).astimezone(timezone.utc))
        if left < right:
            events.append((left, right, row["category"]))
    points = sorted({p for left, right, _ in events for p in (left, right)})
    minutes = {category.value: 0.0 for category in Category}
    for left, right in zip(points, points[1:]):
        categories = {category for begin, finish, category in events if begin < right and finish > left}
        if categories:
            share = (right-left).total_seconds()/60/len(categories)
            for category in categories:
                minutes[category] += share
    total = sum(minutes.values())
    return {"date": day.isoformat(), "timezone": tz, "metric": "planned_time",
            "overlap_policy": "equal_share_by_category", "planned_minutes": round(total, 2),
            "categories": [{"category": cat, "minutes": round(value, 2),
                            "percentage": round(value/total*100, 2) if total else 0}
                           for cat, value in minutes.items()]}
