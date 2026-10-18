"""Durable at-most-once task creation for trusted WhatsApp plans.

An ambiguous provider write stays pending and requires reconciliation rather than
issuing another insert. Google Tasks does not accept a caller-chosen task ID.
"""
import hashlib
import json

from fastapi import HTTPException
from google.oauth2.credentials import Credentials

from backend.schemas import ActivityStatus, ExecuteResponse
from .config import GOOGLE_TOKEN_URI, TASKS_SCOPES
from .oauth import GoogleOAuthService, GoogleReconnectRequired
from .schemas import build_task_action_from_activity
from .tasks import GoogleTasksService, TaskAPIError, TaskValidationError


def execute_tasks(settings, gateway, request, *, action_indexes=None):
    from .execution import _response
    activities = request.activities
    indexes = list(range(len(activities))) if action_indexes is None else action_indexes
    if not settings.google.enable_tasks:
        return _response(activities, ActivityStatus.needs_clarification, 'Google Tasks is not enabled yet.')
    user_id = str(request.user_id)
    try:
        actions = [build_task_action_from_activity(item.model_dump(mode='json'), user_id=user_id,
                   action_id=f'whatsapp:{request.message_id}:{index}', approved=True)
                   for index, item in zip(indexes, activities)]
    except (ValueError, TypeError, TaskValidationError):
        return _response(activities, ActivityStatus.needs_clarification, 'Clarify the task title, category, or due date first.')
    record = gateway.load(user_id)
    if not record:
        return _response(activities, ActivityStatus.needs_clarification, 'Connect Google Calendar and Tasks in TimeSlice Settings first.')
    try:
        credentials = Credentials.from_authorized_user_info({**record['credentials'],
            'client_id': settings.google.client_id, 'client_secret': settings.google.client_secret, 'token_uri': GOOGLE_TOKEN_URI})
    except (ValueError, KeyError):
        return _response(activities, ActivityStatus.needs_clarification, 'Reconnect Google in TimeSlice Settings.')
    if not credentials.has_scopes(TASKS_SCOPES):
        return _response(activities, ActivityStatus.needs_clarification, 'Reconnect Google and approve Google Tasks permission.')
    service = GoogleTasksService(user_id=user_id, credentials=credentials, oauth=GoogleOAuthService(settings.google, required_scopes=TASKS_SCOPES))
    results = []
    stopped = False
    try:
        for item, action in zip(activities, actions):
            external_id = None
            if not stopped:
                try:
                    digest = hashlib.sha256(json.dumps(action.task.google_body(), sort_keys=True).encode()).hexdigest()
                    reservation = gateway._call('POST', '/rest/v1/rpc/timeslice_reserve_task', json={
                        'p_user_id': user_id, 'p_action_id': action.action_id, 'p_payload_hash': digest})[0]
                    if reservation['payload_hash'] != digest:
                        raise TaskAPIError('This message was already used for a different plan.')
                    if reservation['external_id']:
                        external_id = reservation['external_id']
                    elif reservation['reserved']:
                        result = service.execute(action)
                        external_id = result.external_id
                        gateway._call('PATCH', '/rest/v1/timeslice_task_executions',
                            params={'user_id': f'eq.{user_id}', 'action_id': f'eq.{action.action_id}'},
                            json={'external_id': external_id})
                    else:
                        raise TaskAPIError('Previous write is pending reconciliation.')
                except (TaskAPIError, GoogleReconnectRequired, HTTPException):
                    stopped = True
            results.append(item.model_copy(update={'external_id': external_id,
                'status': ActivityStatus.completed if external_id else ActivityStatus.failed}))
        success = all(item.status == ActivityStatus.completed for item in results)
        reply = '\n'.join(f"{'Added task' if item.status == ActivityStatus.completed else 'Could not confirm task'}: {item.title}" for item in results)
        if not success:
            reply += '\nCheck Google Tasks before resubmitting. Uncertain writes are held to prevent duplicates.'
        return ExecuteResponse(results=results, success=success, whatsapp_reply=reply)
    finally:
        try:
            gateway.save(user_id, record['google_sub'], credentials)
        finally:
            service.close()
