"""Multi-user account/token isolation tests; no external services contacted."""

from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from backend.integrations.google.config import GoogleConfig, GOOGLE_TOKEN_URI
from backend.integrations.google.public_app import PublicSettings, SupabaseGateway, create_public_app

MODULE = 'backend.integrations.google.public_app'
USER_ONE = '11111111-1111-4111-8111-111111111111'
USER_TWO = '22222222-2222-4222-8222-222222222222'


def user(user_id=USER_ONE, subject='google-one'):
    return {'id': user_id, 'email': 'demo@example.com', 'email_confirmed_at': '2026-10-17T12:00:00Z',
            'identities': [{'provider': 'google', 'identity_data': {'sub': subject}}]}


def settings():
    return PublicSettings(supabase_url='https://test.supabase.co', supabase_secret_key='sb_secret_test',
                          encryption_key=Fernet.generate_key().decode(),
                          google=GoogleConfig(client_id='test-client', client_secret='private-secret'))


def google_response(data, ok=True):
    response = Mock(ok=ok)
    response.json.return_value = data
    return response


class PublicAPITests(unittest.TestCase):
    def setUp(self):
        self.settings = settings()
        patcher = patch(f'{MODULE}.SupabaseGateway')
        self.gateway = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.gateway.user.return_value = user()
        self.gateway.load.return_value = None
        self.client = TestClient(create_public_app(self.settings))
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer app-session'}

    def google(self, *, subject='google-one', audience='test-client', scopes=None):
        return patch(f'{MODULE}.requests.get', side_effect=[
            google_response({'sub': subject}),
            google_response({'aud': audience, 'scope': ' '.join(self.settings.google.scopes if scopes is None else scopes), 'expires_in': '3600'}),
        ])

    def test_anonymous_requests_cannot_read_connections(self):
        self.assertEqual(self.client.get('/api/google/connection').status_code, 401)
        self.gateway.user.assert_not_called()
        self.gateway.load.assert_not_called()

    def test_user_identity_comes_from_verified_jwt_not_query(self):
        self.client.get('/api/google/connection?user_id=' + USER_TWO, headers=self.headers)
        self.gateway.user.assert_called_once_with('app-session')
        self.gateway.load.assert_called_once_with(USER_ONE)

    def test_connect_validates_google_identity_and_stores_for_authenticated_user(self):
        with self.google():
            response = self.client.put('/api/google/connection', headers=self.headers,
                                       json={'access_token': 'private-access', 'refresh_token': 'private-refresh'})
        self.assertEqual(response.status_code, 200)
        args = self.gateway.save.call_args.args
        self.assertEqual(args[:2], (USER_ONE, 'google-one'))
        self.assertEqual(args[2].refresh_token, 'private-refresh')
        self.assertNotIn('private-', response.text)

    def test_wrong_google_account_or_client_cannot_be_connected(self):
        for change in ({'subject': 'other-account'}, {'audience': 'other-client'}):
            with self.subTest(change=change), self.google(**change):
                response = self.client.put('/api/google/connection', headers=self.headers,
                                           json={'access_token': 'private-access', 'refresh_token': 'private-refresh'})
                self.assertEqual(response.status_code, 403)
        self.gateway.save.assert_not_called()

    def test_missing_calendar_scope_rejected(self):
        with self.google(scopes=['openid', 'email']):
            response = self.client.put('/api/google/connection', headers=self.headers,
                                       json={'access_token': 'private-access', 'refresh_token': 'private-refresh'})
        self.assertEqual(response.status_code, 409)
        self.gateway.save.assert_not_called()

    def test_missing_offline_access_cannot_silently_connect(self):
        with self.google():
            response = self.client.put('/api/google/connection', headers=self.headers,
                                       json={'access_token': 'private-access'})
        self.assertEqual(response.status_code, 409)

    def test_invalid_body_does_not_echo_provider_tokens(self):
        response = self.client.put('/api/google/connection', headers=self.headers,
                                   json={'refresh_token': 'private-refresh'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('private-refresh', response.text)

    def test_disconnect_deletes_only_current_user(self):
        result = self.client.delete('/api/google/connection?user_id=' + USER_TWO, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.gateway.delete.assert_called_once_with(USER_ONE)

    def test_unconnected_user_cannot_read_events(self):
        result = self.client.get('/api/google/events', headers=self.headers,
                                 params={'start_time': '2026-10-17T00:00:00Z', 'end_time': '2026-10-18T00:00:00Z'})
        self.assertEqual(result.status_code, 409)

    def test_reading_events_preserves_category_but_hides_provider_credentials(self):
        expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        creds = Credentials(token='private-access', refresh_token='private-refresh',
                            client_id='test-client', client_secret='private-secret', token_uri=GOOGLE_TOKEN_URI,
                            scopes=list(self.settings.google.scopes), expiry=expires)
        self.gateway.load.return_value = {'google_sub': 'google-one', 'credentials': json.loads(creds.to_json())}
        with patch(f'{MODULE}.GoogleCalendarService') as calendar:
            calendar.return_value.list_events.return_value = [{'id': 'event-one', 'summary': 'Study',
                'start': {'dateTime': '2026-10-17T09:00:00Z'}, 'end': {'dateTime': '2026-10-17T10:00:00Z'},
                'extendedProperties': {'private': {'timeslice_category': 'academics', 'secret': 'private-metadata'}}}]
            response = self.client.get('/api/google/events', headers=self.headers,
                params={'start_time': '2026-10-17T00:00:00Z', 'end_time': '2026-10-18T00:00:00Z'})
            calendar.return_value.close.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['events'][0]['category'], 'academics')
        self.assertNotIn('private-', response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store, private')


class EncryptedStorageTests(unittest.TestCase):
    def setUp(self):
        self.settings = settings()
        self.gateway = SupabaseGateway(self.settings)
        self.credentials = Credentials(token='private-access', refresh_token='private-refresh',
            client_id='test-client', client_secret='private-secret', token_uri=GOOGLE_TOKEN_URI,
            scopes=list(self.settings.google.scopes))

    def test_tokens_are_encrypted_and_round_trip_without_storing_client_secret(self):
        with patch.object(self.gateway, '_call') as call:
            self.gateway.save(USER_ONE, 'google-one', self.credentials)
            row = call.call_args.kwargs['json']
            self.assertNotIn('private-', json.dumps(row))
            decrypted = json.loads(self.gateway.cipher.decrypt(row['credentials_ciphertext'].encode()))
            self.assertNotIn('client_secret', decrypted['credentials'])
            call.return_value = [row]
            result = self.gateway.load(USER_ONE)
            self.assertEqual(result['credentials']['refresh_token'], 'private-refresh')

    def test_ciphertext_cannot_be_moved_to_another_users_row(self):
        envelope = {'user_id': USER_ONE, 'google_sub': 'google-one', 'credentials': {}}
        ciphertext = self.gateway.cipher.encrypt(json.dumps(envelope).encode()).decode()
        with patch.object(self.gateway, '_call', return_value=[{'google_sub': 'google-one', 'credentials_ciphertext': ciphertext}]):
            with self.assertRaises(HTTPException) as caught:
                self.gateway.load(USER_TWO)
            self.assertEqual(caught.exception.status_code, 409)

    def test_unverified_supabase_identity_is_rejected(self):
        with patch.object(self.gateway, '_call', return_value={'id': USER_ONE}):
            with self.assertRaises(HTTPException):
                self.gateway.user('untrusted')


if __name__ == '__main__':
    unittest.main()


class SeparateServicesTests(PublicAPITests):
    def setUp(self):
        super().setUp()
        from dataclasses import replace
        self.settings = replace(self.settings, google=replace(self.settings.google, enable_tasks=True))
        self.client.close()
        self.client = TestClient(create_public_app(self.settings))

    def test_tasks_only_connection_has_independent_status(self):
        from backend.integrations.google.config import TASKS_SCOPES
        self.gateway.load.return_value = {'google_sub': 'google-one', 'credentials': {'scopes': list(TASKS_SCOPES)}}
        data = self.client.get('/api/google/connection', headers=self.headers).json()
        self.assertFalse(data['connected'])
        self.assertTrue(data['tasks_connected'])

    def test_calendar_only_connection_has_independent_status(self):
        from backend.integrations.google.config import CALENDAR_SCOPES
        self.gateway.load.return_value = {'google_sub': 'google-one', 'credentials': {'scopes': list(CALENDAR_SCOPES)}}
        data = self.client.get('/api/google/connection', headers=self.headers).json()
        self.assertTrue(data['calendar_connected'])
        self.assertFalse(data['tasks_connected'])

    def test_tasks_can_connect_without_calendar(self):
        from backend.integrations.google.config import TASKS_SCOPES
        with self.google(scopes=TASKS_SCOPES):
            response = self.client.put('/api/google/connection', headers=self.headers,
                json={'service': 'tasks', 'access_token': 'access', 'refresh_token': 'refresh'})
        self.assertEqual(response.status_code, 200)

    def test_adding_tasks_cannot_discard_calendar_grant(self):
        from backend.integrations.google.config import CALENDAR_SCOPES, TASKS_SCOPES
        self.gateway.load.return_value = {'google_sub': 'google-one', 'credentials': {'scopes': list(CALENDAR_SCOPES)}}
        with self.google(scopes=TASKS_SCOPES):
            response = self.client.put('/api/google/connection', headers=self.headers,
                json={'service': 'tasks', 'access_token': 'access', 'refresh_token': 'refresh'})
        self.assertEqual(response.status_code, 409)
        self.gateway.save.assert_not_called()
