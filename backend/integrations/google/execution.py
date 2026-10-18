"""Real, authenticated AI-to-Google Calendar execution handoff.

The signed Twilio ingress resolves the user and authorizes explicit create intent.
Only Eva's backend, authenticated with AI_SERVICE_TOKEN, may use this route.
OAuth consent or an AI model's approval claim alone cannot execute a plan.
"""

from datetime import timedelta
import os
from pathlib import Path
import secrets
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from google.oauth2.credentials import Credentials
from pydantic import Field, field_validator, model_validator

from backend.schemas import Activity, ActivityStatus, ExecuteRequest, ExecuteResponse
from .availability import TimeSlot, detect_conflicts
from .calendar import CalendarAPIError, CalendarValidationError, GoogleCalendarService, calendar_event_id
from .config import GOOGLE_TOKEN_URI, CALENDAR_SCOPES, TASKS_SCOPES
from .oauth import GoogleOAuthService, GoogleReconnectRequired
from .public_app import PublicSettings, SupabaseGateway
from .schemas import build_calendar_action_from_activity, build_task_action_from_activity


class CalendarExecuteRequest(ExecuteRequest):
    user_id: UUID
    activities: list[Activity] = Field(min_length=1, max_length=30)
    authorization_source: Literal['inbound_whatsapp_create_request']
    message_id: str = Field(min_length=1, max_length=128)
    timezone: str = 'America/New_York'

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError('An IANA timezone is required.') from None
        return value

    @model_validator(mode='after')
    def unique_ids(self):
        if len({item.id for item in self.activities}) != len(self.activities):
            raise ValueError('Activity IDs must be unique.')
        return self


def _response(activities: list[Activity], status: ActivityStatus, reply: str) -> ExecuteResponse:
    return ExecuteResponse(
        results=[item.model_copy(update={'status': status, 'external_id': None}) for item in activities],
        success=False, whatsapp_reply=reply,
    )


class CalendarPlanExecutor:
    def __init__(self, settings: PublicSettings, gateway: SupabaseGateway | None = None):
        self.settings = settings
        self.gateway = gateway or SupabaseGateway(settings)
        self.oauth = GoogleOAuthService(settings.google, required_scopes=CALENDAR_SCOPES)

    def execute(self, request: CalendarExecuteRequest, *, action_indexes=None) -> ExecuteResponse:
        activities = request.activities
        indexes = list(range(len(activities))) if action_indexes is None else action_indexes
        if any(item.status != ActivityStatus.proposed or item.external_id or item.clarification_needed for item in activities):
            return _response(activities, ActivityStatus.needs_clarification,
                             'Nothing was scheduled. Clarify the proposed activities before execution.')
        if all(item.type.value == 'task' for item in activities):
            from .task_execution import execute_tasks
            return execute_tasks(self.settings, self.gateway, request, action_indexes=indexes)
        if any(item.type.value == 'task' for item in activities):
            return self._execute_mixed(request, indexes)
        user_id = str(request.user_id)
        try:
            actions = [build_calendar_action_from_activity(
                item.model_dump(mode='json'), user_id=user_id,
                action_id=f'whatsapp:{request.message_id}:{index}', approved=True,
            ) for index, item in zip(indexes, activities)]
        except (CalendarValidationError, ValueError, TypeError):
            return _response(activities, ActivityStatus.needs_clarification,
                             'Nothing was scheduled. Each event needs a title, category, and exact timezone-aware start and end.')
        slots = [TimeSlot(action.event.start_time, action.event.end_time) for action in actions]
        if max(slot.end_utc() for slot in slots) - min(slot.start_utc() for slot in slots) > timedelta(days=31):
            return _response(activities, ActivityStatus.needs_clarification,
                             'Nothing was scheduled. Split this plan into date ranges of at most 31 days.')
        if any(a.overlaps(b) for i, a in enumerate(slots) for b in slots[i + 1:]):
            return _response(activities, ActivityStatus.needs_clarification,
                             'Nothing was scheduled. Some activities in this plan overlap; please choose separate times.')
        record = self.gateway.load(user_id)
        if record is None:
            return _response(activities, ActivityStatus.needs_clarification,
                             'Nothing was scheduled. Sign in to Offload and connect your Google Calendar first.')
        try:
            credentials = Credentials.from_authorized_user_info({
                **record['credentials'], 'client_id': self.settings.google.client_id,
                'client_secret': self.settings.google.client_secret, 'token_uri': GOOGLE_TOKEN_URI,
            })
        except (ValueError, KeyError):
            return _response(activities, ActivityStatus.needs_clarification,
                             'Nothing was scheduled. Reconnect Google Calendar in Offload Settings.')
        calendar = GoogleCalendarService(user_id=user_id, credentials=credentials, oauth=self.oauth)
        try:
            events = calendar.list_events(start_time=min(slot.start_utc() for slot in slots),
                                          end_time=max(slot.end_utc() for slot in slots))
            # Existing events with these deterministic IDs are previous attempts
            # at these same actions. Calendar creation checks their payload hash.
            own_ids = {calendar_event_id(user_id, 'primary', action.action_id) for action in actions}
            existing = [event for event in events if event.get('id') not in own_ids]
            if any(detect_conflicts(slot, existing, default_tz=ZoneInfo(request.timezone)) for slot in slots):
                return _response(activities, ActivityStatus.needs_clarification,
                                 'Nothing was scheduled. Your Calendar already has an event at one of these times. Please choose another time.')
            results = []
            failed = False
            for item, action in zip(activities, actions):
                if failed:
                    results.append(item.model_copy(update={'status': ActivityStatus.failed, 'external_id': None}))
                    continue
                try:
                    result = calendar.execute(action)
                    results.append(item.model_copy(update={'status': ActivityStatus.completed, 'external_id': result.external_id}))
                except (CalendarAPIError, GoogleReconnectRequired):
                    results.append(item.model_copy(update={'status': ActivityStatus.failed, 'external_id': None}))
                    failed = True
            success = all(item.status == ActivityStatus.completed for item in results)
            reply = '\n'.join(f"{'Added' if item.status == ActivityStatus.completed else 'Could not confirm'}: {item.title}" for item in results)
            if failed:
                reply += '\nSome results could not be confirmed. Retry the same message and plan to avoid duplicate events.'
            return ExecuteResponse(results=results, success=success, whatsapp_reply=reply)
        except GoogleReconnectRequired:
            return _response(activities, ActivityStatus.needs_clarification,
                             'Nothing was scheduled. Reconnect Google Calendar in Offload Settings.')
        except CalendarAPIError:
            return _response(activities, ActivityStatus.failed,
                             'Nothing was scheduled. Calendar availability could not be checked; please try again later.')
        finally:
            try:
                self.gateway.save(user_id, record['google_sub'], credentials)
            finally:
                calendar.close()


    def _execute_mixed(self, request, indexes):
        # Validate task contents and grant before Calendar writes. Calendar
        # validation and availability checks still run before any provider write.
        user_id = str(request.user_id)
        try:
            for index, item in zip(indexes, request.activities):
                if item.type.value == 'task':
                    build_task_action_from_activity(item.model_dump(mode='json'), user_id=user_id,
                        action_id=f'whatsapp:{request.message_id}:{index}', approved=True)
        except (ValueError, TypeError):
            return _response(request.activities, ActivityStatus.needs_clarification, 'Nothing was scheduled. Clarify the task title or due date.')
        record = self.gateway.load(user_id)
        if not self.settings.google.enable_tasks or not record or not set(TASKS_SCOPES).issubset(record['credentials'].get('scopes', [])):
            return _response(request.activities, ActivityStatus.needs_clarification, 'Nothing was scheduled. Connect Google Calendar and Tasks in Settings first.')
        event_pairs = [(index, item) for index, item in zip(indexes, request.activities) if item.type.value == 'event']
        task_pairs = [(index, item) for index, item in zip(indexes, request.activities) if item.type.value == 'task']
        events = self.execute(request.model_copy(update={'activities': [item for _, item in event_pairs]}),
                              action_indexes=[index for index, _ in event_pairs])
        if events.success:
            tasks = self.execute(request.model_copy(update={'activities': [item for _, item in task_pairs]}),
                                 action_indexes=[index for index, _ in task_pairs])
        else:
            tasks = _response([item for _, item in task_pairs], ActivityStatus.needs_clarification,
                              'Tasks were not attempted because the Calendar plan needs attention.')
        by_id = {item.id: item for item in events.results + tasks.results}
        return ExecuteResponse(results=[by_id[item.id] for item in request.activities],
            success=events.success and tasks.success, whatsapp_reply=events.whatsapp_reply + '\n' + tasks.whatsapp_reply)


def create_execution_router() -> APIRouter:
    router = APIRouter()

    def trusted_service(request: Request):
        load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
        expected = os.environ.get('AI_SERVICE_TOKEN', '')
        if not expected:
            raise HTTPException(503, 'Calendar execution service authentication is not configured.')
        actual = request.headers.get('authorization', '')
        if not secrets.compare_digest(actual.encode('utf-8'), f'Bearer {expected}'.encode('utf-8')):
            raise HTTPException(401, 'Internal service authentication is required.')

    @router.post('/api/execute', response_model=ExecuteResponse, dependencies=[Depends(trusted_service)])
    def execute(request: CalendarExecuteRequest):
        try:
            settings = PublicSettings.from_env()
        except ValueError:
            raise HTTPException(503, 'Google Calendar and account storage are not configured yet.') from None
        return CalendarPlanExecutor(settings).execute(request)

    return router
