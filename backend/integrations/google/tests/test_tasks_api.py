from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from dataclasses import replace

from backend.integrations.google.public_app import create_public_app
from backend.integrations.google.tests.test_public_app import settings, user


def test_tasks_are_bound_to_verified_user_and_never_expose_tokens():
    config = settings()
    config = replace(config, google=replace(config.google, enable_tasks=True))
    with patch('backend.integrations.google.public_app.SupabaseGateway') as gateway, \
         patch('backend.integrations.google.public_app.GoogleTasksService') as service:
        gateway.return_value.user.return_value = user()
        gateway.return_value.load.return_value = {'google_sub': 'google-one', 'credentials': {
            'refresh_token': 'private-refresh', 'scopes': ['https://www.googleapis.com/auth/tasks']}}
        service.return_value.list_tasks.return_value = [{'id': 'task-one', 'title': 'Submit essay',
            'notes': 'private notes', 'due': '2026-10-22T00:00:00Z'}]
        with TestClient(create_public_app(config)) as client:
            assert client.get('/api/google/tasks').status_code == 401
            response = client.get('/api/google/tasks?user_id=other', headers={'Authorization': 'Bearer app-token'})
        assert response.status_code == 200
        assert response.json()['tasks'][0]['external_id'] == 'task-one'
        assert 'private' not in response.text
        assert service.call_args.kwargs['user_id'] == user()['id']
        service.return_value.close.assert_called_once()


def test_calendar_only_grant_cannot_read_tasks():
    config = settings()
    config = replace(config, google=replace(config.google, enable_tasks=True))
    with patch('backend.integrations.google.public_app.SupabaseGateway') as gateway, \
         patch('backend.integrations.google.public_app.GoogleTasksService') as service:
        gateway.return_value.user.return_value = user()
        gateway.return_value.load.return_value = {'google_sub': 'google-one', 'credentials': {
            'refresh_token': 'refresh', 'scopes': list(config.google.scopes[:2])}}
        with TestClient(create_public_app(config)) as client:
            assert client.get('/api/google/tasks', headers={'Authorization': 'Bearer app-token'}).status_code == 409
        service.assert_not_called()
