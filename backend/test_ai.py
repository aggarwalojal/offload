"""
Quick verification test script for TimeSlice AI schemas and planner.
Can run without API keys to verify schemas and validation logic.
"""

from datetime import datetime, timedelta
import pytz
from backend.schemas import (
    Activity,
    ActivityCategory,
    ActivityType,
    ActivityStatus,
    ParseRequest,
    ParseResponse,
)
from backend.ai.planner import validate_and_plan


def test_schemas():
    print("Testing Pydantic Schemas...")
    est = pytz.timezone("America/New_York")
    now = datetime.now(est)

    act = Activity(
        type=ActivityType.event,
        title="CS 1331 Java Project",
        category=ActivityCategory.academics,
        start_time=now,
        end_time=now + timedelta(hours=2),
        duration_minutes=120,
        status=ActivityStatus.proposed,
    )

    data = act.model_dump(mode="json")
    assert data["type"] == "event"
    assert data["category"] == "academics"
    assert data["duration_minutes"] == 120
    assert "start_time" in data
    print("✓ Activity schema model_dump successful!")
    print(f"  Sample JSON: {data}\n")


def test_conflict_detection():
    print("Testing Planner Conflict Detection...")
    est = pytz.timezone("America/New_York")
    base = datetime.now(est).replace(hour=14, minute=0, second=0, microsecond=0)

    e1 = Activity(
        type=ActivityType.event,
        title="Study Group",
        category=ActivityCategory.academics,
        start_time=base,
        end_time=base + timedelta(hours=2),  # 2:00 PM - 4:00 PM
    )
    e2 = Activity(
        type=ActivityType.event,
        title="Club Meeting",
        category=ActivityCategory.social,
        start_time=base + timedelta(hours=1),  # 3:00 PM - 4:00 PM (OVERLAP!)
        end_time=base + timedelta(hours=2),
    )

    validated, warnings = validate_and_plan([e1, e2])
    assert len(warnings) > 0, "Conflict should have been detected!"
    print(f"✓ Conflict detected successfully: {warnings[0]}\n")


if __name__ == "__main__":
    test_schemas()
    test_conflict_detection()
    print("All basic schema and planner tests passed!")
