"""Integration schemas and transformers for TimeSlice Google Workspace execution.

Validates incoming activity plans, converts them to authorized Calendar/Task actions,
and returns normalized external Google IDs for database synchronization.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

from .calendar import CalendarAction, CalendarEventInput, CalendarValidationError
from .tasks import TaskAction, TaskInput, TaskValidationError

CATEGORIES = frozenset({"academics", "career", "social", "health", "admin"})


@dataclass(frozen=True)
class GoogleExecutionResult:
    """Standardized response from Google Workspace execution for database sync."""

    action_id: str
    activity_type: Literal["event", "task"]
    external_id: str
    status: Literal["completed", "failed"] = "completed"
    error: Optional[str] = None
    container_id: str = "primary"  # Calendar ID or TaskList ID
    raw_response: Optional[dict[str, Any]] = field(default=None, repr=False)


def build_calendar_action_from_activity(
    activity: dict[str, Any],
    *,
    user_id: str,
    action_id: str | None = None,
    approved: bool = True,
    calendar_id: str = "primary",
) -> CalendarAction:
    """Builds a validated CalendarAction from a normalized TimeSlice event object."""
    act_id = action_id or activity.get("id")
    if not act_id or not isinstance(act_id, str):
        raise CalendarValidationError("action_id or activity.id is required.")

    title = activity.get("title")
    category = activity.get("category")
    start_time_val = activity.get("start_time")
    end_time_val = activity.get("end_time")

    if isinstance(start_time_val, str):
        start_time = datetime.fromisoformat(start_time_val)
    elif isinstance(start_time_val, datetime):
        start_time = start_time_val
    else:
        raise CalendarValidationError("Event start_time is required.")

    if isinstance(end_time_val, str):
        end_time = datetime.fromisoformat(end_time_val)
    elif isinstance(end_time_val, datetime):
        end_time = end_time_val
    else:
        raise CalendarValidationError("Event end_time is required.")

    event_input = CalendarEventInput(
        title=str(title),
        category=str(category),
        start_time=start_time,
        end_time=end_time,
        description=activity.get("description", ""),
    )

    return CalendarAction(
        action_id=act_id,
        user_id=user_id,
        operation="create",
        approved=approved,
        calendar_id=calendar_id,
        event=event_input,
    )


def build_task_action_from_activity(
    activity: dict[str, Any],
    *,
    user_id: str,
    action_id: str | None = None,
    approved: bool = True,
    task_list_id: str = "@default",
) -> TaskAction:
    """Builds a validated TaskAction from a normalized TimeSlice task object."""
    act_id = action_id or activity.get("id")
    if not act_id or not isinstance(act_id, str):
        raise TaskValidationError("action_id or activity.id is required.")

    title = activity.get("title")
    category = activity.get("category")
    due = activity.get("due_date") or activity.get("due")

    task_input = TaskInput(
        title=str(title),
        category=str(category),
        notes=activity.get("notes", ""),
        due=due,
    )

    return TaskAction(
        action_id=act_id,
        user_id=user_id,
        operation="create",
        approved=approved,
        task_list_id=task_list_id,
        task=task_input,
    )
