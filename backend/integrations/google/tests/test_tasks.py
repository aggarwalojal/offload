"""Unit tests for Google Tasks service operations."""

from datetime import date, datetime, timezone
import unittest
from unittest.mock import Mock, patch

from backend.integrations.google.tasks import (
    GoogleTasksService,
    TaskAction,
    TaskAPIError,
    TaskAuthorizationError,
    TaskConflictError,
    TaskInput,
    TaskResult,
    TaskValidationError,
)

MODULE = "backend.integrations.google.tasks"


def response(payload=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = {} if payload is None else payload
    return result


class GoogleTasksTests(unittest.TestCase):
    def setUp(self):
        self.transport_patch = patch(f"{MODULE}.AuthorizedSession")
        self.session = self.transport_patch.start().return_value
        self.addCleanup(self.transport_patch.stop)

        self.oauth = Mock()
        self.credentials = Mock()
        self.service = GoogleTasksService(
            user_id="user-one", credentials=self.credentials, oauth=self.oauth
        )
        self.task_input = TaskInput(
            title="Submit IBM Internship Application",
            category="career",
            notes="Requires resume upload",
            due=date(2026, 10, 19),
        )
        self.action = TaskAction(
            action_id="task-action-1",
            user_id="user-one",
            operation="create",
            approved=True,
            task=self.task_input,
        )

    def test_task_input_validation(self):
        # Empty title rejected
        with self.assertRaises(TaskValidationError):
            TaskInput(title="", category="career")

        # Unknown category rejected
        with self.assertRaises(TaskValidationError):
            TaskInput(title="Valid", category="nonexistent")

        # Invalid due format rejected
        with self.assertRaises(TaskValidationError):
            TaskInput(title="Valid", category="career", due="not-a-date")

        # Valid formatting
        body = self.task_input.google_body()
        self.assertEqual(body["title"], "Submit IBM Internship Application")
        self.assertIn("[TimeSlice:career]", body["notes"])
        self.assertEqual(body["due"], "2026-10-19T00:00:00.000Z")

    def test_unapproved_or_wrong_user_rejected(self):
        unapproved = TaskAction(
            action_id="t1", user_id="user-one", operation="create", approved=False, task=self.task_input
        )
        with self.assertRaises(TaskAuthorizationError):
            self.service.execute(unapproved)

        wrong_user = TaskAction(
            action_id="t1", user_id="user-two", operation="create", approved=True, task=self.task_input
        )
        with self.assertRaises(TaskAuthorizationError):
            self.service.execute(wrong_user)

    def test_create_task_success(self):
        self.session.request.return_value = response({"id": "google-task-id-123", "title": "Submit IBM"})
        res = self.service.execute(self.action)

        self.assertEqual(res.external_id, "google-task-id-123")
        self.assertEqual(res.status, "completed")
        self.assertEqual(res.task_list_id, "@default")

    def test_delete_task_success(self):
        del_action = TaskAction(
            action_id="del-1",
            user_id="user-one",
            operation="delete",
            approved=True,
            task_id="google-task-id-123",
        )
        self.session.request.return_value = response(status=204)
        res = self.service.execute(del_action)

        self.assertEqual(res.external_id, "google-task-id-123")
        self.assertEqual(res.status, "completed")

    def test_complete_task_success(self):
        comp_action = TaskAction(
            action_id="comp-1",
            user_id="user-one",
            operation="complete",
            approved=True,
            task_id="google-task-id-123",
        )
        self.session.request.return_value = response({"id": "google-task-id-123", "status": "completed"})
        res = self.service.execute(comp_action)

        self.assertEqual(res.external_id, "google-task-id-123")
        self.assertEqual(res.status, "completed")

    def test_list_tasks_success(self):
        self.session.request.return_value = response({
            "items": [
                {"id": "t1", "title": "Task 1", "deleted": False},
                {"id": "t2", "title": "Task 2", "deleted": True},
            ]
        })
        tasks = self.service.list_tasks()
        # Deleted tasks filtered out
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], "t1")


if __name__ == "__main__":
    unittest.main()
