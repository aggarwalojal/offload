"""Unit tests for Google integration schemas and activity conversion."""

from datetime import datetime, timedelta, timezone
import unittest

from backend.integrations.google.calendar import CalendarValidationError
from backend.integrations.google.schemas import (
    GoogleExecutionResult,
    build_calendar_action_from_activity,
    build_task_action_from_activity,
)
from backend.integrations.google.tasks import TaskValidationError

EDT = timezone(timedelta(hours=-4))


class GoogleSchemasTests(unittest.TestCase):
    def test_build_calendar_action_success(self):
        activity = {
            "id": "act-study-java",
            "type": "event",
            "title": "Study Java",
            "category": "academics",
            "start_time": "2026-10-18T19:00:00-04:00",
            "end_time": "2026-10-18T21:00:00-04:00",
            "description": "CS 1331 project work",
        }
        action = build_calendar_action_from_activity(activity, user_id="user-123")

        self.assertEqual(action.action_id, "act-study-java")
        self.assertEqual(action.user_id, "user-123")
        self.assertEqual(action.operation, "create")
        self.assertTrue(action.approved)
        self.assertEqual(action.event.title, "Study Java")
        self.assertEqual(action.event.category, "academics")
        duration = int((action.event.end_time - action.event.start_time).total_seconds() // 60)
        self.assertEqual(duration, 120)

    def test_build_calendar_action_missing_times(self):
        activity = {
            "id": "act-invalid",
            "title": "Study Java",
            "category": "academics",
        }
        with self.assertRaises(CalendarValidationError):
            build_calendar_action_from_activity(activity, user_id="user-123")

    def test_build_task_action_success(self):
        activity = {
            "id": "act-apply-ibm",
            "type": "task",
            "title": "Apply to IBM Internship",
            "category": "career",
            "due_date": "2026-10-19",
        }
        action = build_task_action_from_activity(activity, user_id="user-123")

        self.assertEqual(action.action_id, "act-apply-ibm")
        self.assertEqual(action.user_id, "user-123")
        self.assertEqual(action.operation, "create")
        self.assertTrue(action.approved)
        self.assertEqual(action.task.title, "Apply to IBM Internship")
        self.assertEqual(action.task.category, "career")

    def test_google_execution_result_dataclass(self):
        res = GoogleExecutionResult(
            action_id="act-1",
            activity_type="event",
            external_id="google-event-789",
            status="completed",
        )
        self.assertEqual(res.external_id, "google-event-789")
        self.assertEqual(res.status, "completed")
        self.assertIsNone(res.error)


if __name__ == "__main__":
    unittest.main()
