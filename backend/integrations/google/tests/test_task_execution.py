import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from backend.integrations.google.execution import CalendarPlanExecutor
from backend.integrations.google.tests.test_execution import plan
from backend.integrations.google.tests.test_public_app import settings
from backend.integrations.google.tasks import TaskAPIError


class TaskExecutionTests(unittest.TestCase):
    def setUp(self):
        self.settings = settings()
        self.settings = replace(self.settings, google=replace(self.settings.google, enable_tasks=True))
        self.gateway = Mock()
        self.gateway.load.return_value = {'google_sub': 'one', 'credentials': {
            'refresh_token': 'refresh', 'scopes': ['https://www.googleapis.com/auth/tasks']}}
        self.request = plan(activities=[dict(id='one', type='task', title='Submit essay', category='academics', due_date='2026-10-22')])
        body = {'title': 'Submit essay', 'notes': '[TimeSlice:academics]', 'due': '2026-10-22T00:00:00.000Z'}
        self.reservation = dict(payload_hash=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
                                external_id=None, reserved=True)
        self.gateway._call.return_value = [self.reservation]
        patcher = patch('backend.integrations.google.task_execution.GoogleTasksService')
        self.service = patcher.start().return_value
        self.service.execute.return_value = Mock(external_id='google-task-id')
        self.addCleanup(patcher.stop)

    def run_plan(self):
        return CalendarPlanExecutor(self.settings, self.gateway).execute(self.request)

    def test_create_and_persist_actual_id(self):
        response = self.run_plan()
        self.assertTrue(response.success)
        self.assertEqual(response.results[0].external_id, 'google-task-id')
        self.assertEqual(self.gateway._call.call_args.args[0], 'PATCH')
        self.service.close.assert_called_once()

    def test_completed_retry_does_not_insert_again(self):
        self.reservation.update(external_id='previous-id', reserved=False)
        self.assertEqual(self.run_plan().results[0].external_id, 'previous-id')
        self.service.execute.assert_not_called()

    def test_pending_retry_never_inserts(self):
        self.reservation['reserved'] = False
        self.assertFalse(self.run_plan().success)
        self.service.execute.assert_not_called()

    def test_changed_payload_cannot_reuse_message(self):
        self.reservation['payload_hash'] = 'other'
        self.assertFalse(self.run_plan().success)
        self.service.execute.assert_not_called()

    def test_uncertain_write_has_no_fake_success(self):
        self.service.execute.side_effect = TaskAPIError('timeout')
        result = self.run_plan()
        self.assertFalse(result.success)
        self.assertIsNone(result.results[0].external_id)

    def test_missing_scope_requires_reconnect(self):
        self.gateway.load.return_value['credentials']['scopes'] = []
        self.assertFalse(self.run_plan().success)
        self.service.execute.assert_not_called()

    def test_disabled_tasks_never_loads_credentials(self):
        self.settings = replace(self.settings, google=replace(self.settings.google, enable_tasks=False))
        self.assertFalse(self.run_plan().success)
        self.gateway.load.assert_not_called()
