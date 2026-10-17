"""
Action Planner & Conflict Detector for TimeSlice.
Validates proposed activities, verifies start/end times, and detects overlaps.
"""

from typing import List, Tuple
from datetime import datetime
from backend.schemas import Activity, ActivityType, ActivityStatus


def validate_and_plan(activities: List[Activity]) -> Tuple[List[Activity], List[str]]:
    """
    Validates a list of activities before handoff to Google Calendar / Google Tasks.
    Returns:
        (validated_activities, warnings_or_clarifications)
    """
    warnings: List[str] = []
    events: List[Activity] = []

    for act in activities:
        if act.type == ActivityType.event:
            # Events require start_time and end_time
            if not act.start_time:
                act.status = ActivityStatus.needs_clarification
                msg = f"'{act.title}' requires a start time to block on Google Calendar."
                act.clarification_needed = msg
                warnings.append(msg)
            elif not act.end_time:
                # Default to 60 min if end time is missing
                from datetime import timedelta
                act.end_time = act.start_time + timedelta(minutes=60)
                act.duration_minutes = 60

            events.append(act)

    # Check for internal conflicts between proposed events
    events_with_time = [e for e in events if e.start_time and e.end_time]
    events_sorted = sorted(events_with_time, key=lambda x: x.start_time)

    for i in range(len(events_sorted) - 1):
        curr = events_sorted[i]
        nxt = events_sorted[i + 1]
        if curr.end_time > nxt.start_time:
            conflict_msg = (
                f"Scheduling conflict detected between '{curr.title}' ({curr.start_time.strftime('%I:%M %p')}) "
                f"and '{nxt.title}' ({nxt.start_time.strftime('%I:%M %p')})."
            )
            warnings.append(conflict_msg)
            nxt.clarification_needed = conflict_msg

    return activities, warnings
