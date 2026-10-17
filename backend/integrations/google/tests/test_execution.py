"""Execution boundary tests without network or real Calendar writes."""
import os
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.integrations.google.execution import CalendarExecuteRequest, CalendarPlanExecutor, create_execution_router
from backend.integrations.google.calendar import CalendarAPIError
from backend.integrations.google.tests.test_public_app import settings, USER_ONE

MODULE = 'backend.integrations.google.execution'


def plan(**updates):
    data = dict(user_id=USER_ONE, message_id='SM-one', authorization_source='inbound_whatsapp_create_request',
                activities=[dict(id='activity-one', type='event', title='Study calculus', category='academics',
                                 start_time='2026-10-20T14:00:00-04:00', end_time='2026-10-20T15:00:00-04:00')])
    data.update(updates)
    return CalendarExecuteRequest.model_validate(data)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.gateway = Mock()
        self.gateway.load.return_value = {'google_sub': 'google-one', 'credentials': {'refresh_token': 'refresh'}}
        self.executor = CalendarPlanExecutor(settings(), self.gateway)
        patcher = patch(f'{MODULE}.GoogleCalendarService')
        self.calendar = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.calendar.list_events.return_value = []
        self.calendar.execute.return_value = Mock(external_id='real-google-id')

    def test_success_uses_real_result_and_preserves_activity(self):
        request = plan()
        response = self.executor.execute(request)
        self.assertTrue(response.success)
        self.assertEqual(response.results[0].external_id, 'real-google-id')
        self.assertEqual(response.results[0].title, request.activities[0].title)
        self.gateway.load.assert_called_once_with(USER_ONE)
        self.gateway.save.assert_called_once()
        self.calendar.close.assert_called_once()

    def test_retry_action_identity_survives_ai_regenerated_uuid(self):
        request = plan()
        self.executor.execute(request)
        first = self.calendar.execute.call_args.args[0].action_id
        request.activities[0].id = 'regenerated-id'
        self.executor.execute(request)
        self.assertEqual(first, self.calendar.execute.call_args.args[0].action_id)

    def test_missing_connection_never_claims_success(self):
        self.gateway.load.return_value = None
        self.assertFalse(self.executor.execute(plan()).success)
        self.calendar.execute.assert_not_called()

    def test_invalid_times_never_load_credentials(self):
        request = plan()
        request.activities[0].start_time = None
        self.assertFalse(self.executor.execute(request).success)
        self.gateway.load.assert_not_called()

    def test_calendar_conflict_prevents_write(self):
        self.calendar.list_events.return_value = [{'id': 'other', 'start': {'dateTime': '2026-10-20T14:30:00-04:00'},
                                                  'end': {'dateTime': '2026-10-20T16:00:00-04:00'}}]
        self.assertFalse(self.executor.execute(plan()).success)
        self.calendar.execute.assert_not_called()

    def test_write_failure_has_no_invented_external_id(self):
        self.calendar.execute.side_effect = CalendarAPIError('Unavailable')
        response = self.executor.execute(plan())
        self.assertFalse(response.success)
        self.assertIsNone(response.results[0].external_id)

    def test_route_rejects_untrusted_requests(self):
        app = FastAPI()
        app.include_router(create_execution_router())
        with patch.dict(os.environ, {'AI_SERVICE_TOKEN': 'test-secret'}), TestClient(app) as client:
            self.assertEqual(client.post('/api/execute', json=plan().model_dump(mode='json')).status_code, 401)
            data = plan().model_dump(mode='json')
            data['authorization_source'] = 'model_says_approved'
            self.assertEqual(client.post('/api/execute', json=data,
                                        headers={'Authorization': 'Bearer test-secret'}).status_code, 422)
