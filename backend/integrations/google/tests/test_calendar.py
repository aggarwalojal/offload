"""Offline Google Calendar tests: all HTTP calls are mocked."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from google.auth.exceptions import RefreshError
from requests.exceptions import ConnectionError

from backend.integrations.google.calendar import (
    CalendarAction, CalendarAPIError, CalendarAuthorizationError,
    CalendarConflictError, CalendarEventInput, CalendarValidationError,
    GoogleCalendarService,
)
from backend.integrations.google.oauth import GoogleReconnectRequired

MODULE = "backend.integrations.google.calendar"


def response(payload=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = {} if payload is None else payload
    return result


class GoogleCalendarTests(unittest.TestCase):
    def setUp(self):
        self.transport_patch = patch(f"{MODULE}.AuthorizedSession")
        self.session = self.transport_patch.start().return_value
        self.addCleanup(self.transport_patch.stop)
        self.oauth = Mock()
        self.credentials = Mock()
        self.service = GoogleCalendarService(
            user_id="user-one", credentials=self.credentials, oauth=self.oauth
        )
        self.start = datetime(2026, 10, 18, 19, tzinfo=timezone(timedelta(hours=-4)))
        self.end = self.start + timedelta(hours=2)
        self.event = CalendarEventInput(
            title="Study Java", category="academics", start_time=self.start, end_time=self.end
        )
        self.action = CalendarAction(
            action_id="action-one", user_id="user-one", operation="create",
            approved=True, event=self.event,
        )

    def existing(self, **overrides):
        return {
            "id": "google-event", "etag": '"version-one"',
            "start": {"dateTime": self.start.isoformat()},
            "end": {"dateTime": self.end.isoformat()},
            **overrides,
        }

    def test_invalid_event_inputs(self):
        for change in ({"title": " "}, {"category": "unknown"},
                       {"start_time": self.start.replace(tzinfo=None)},
                       {"end_time": self.start}, {"end_time": self.start - timedelta(hours=1)}):
            with self.subTest(change=change), self.assertRaises(CalendarValidationError):
                replace(self.event, **change)
        self.session.request.assert_not_called()

    def test_dst_window_compares_instants(self):
        ny = ZoneInfo("America/New_York")
        start = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=0)
        end = datetime(2026, 11, 1, 1, 15, tzinfo=ny, fold=1)
        event = replace(self.event, start_time=start, end_time=end)
        self.assertIn("-05:00", event.google_body()["end"]["dateTime"])

    def test_action_shape_validation(self):
        for change in ({"event": None}, {"operation": "other"}, {"approved": "true"},
                       {"operation": "delete", "event": None},
                       {"event_id": "unexpected"}):
            with self.subTest(change=change), self.assertRaises(CalendarValidationError):
                replace(self.action, **change)

    def test_unapproved_or_wrong_user_never_contacts_google(self):
        for change in ({"approved": False}, {"user_id": "user-two"}):
            with self.subTest(change=change), self.assertRaises(CalendarAuthorizationError):
                self.service.execute(replace(self.action, **change))
        self.session.request.assert_not_called()
        self.oauth.refresh_credentials.assert_not_called()

    def test_list_events_paginates_and_preserves_all_day_values(self):
        all_day = {"id": "all-day", "start": {"date": "2026-10-18"},
                   "end": {"date": "2026-10-19"}}
        self.session.request.side_effect = [
            response({"items": [self.existing()], "nextPageToken": "next"}),
            response({"items": [all_day, {"id": "deleted", "status": "cancelled"}]}),
        ]
        events = self.service.list_events(start_time=self.start, end_time=self.end)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1], all_day)
        params = self.session.request.call_args.kwargs["params"]
        self.assertEqual(params["pageToken"], "next")
        self.assertEqual(params["singleEvents"], "true")
        self.assertEqual(params["timeMin"], self.start.isoformat())

    def test_invalid_window_does_not_contact_google(self):
        with self.assertRaises(CalendarValidationError):
            self.service.list_events(start_time=self.end, end_time=self.start)
        self.session.request.assert_not_called()

    def test_repeated_page_token_fails_without_looping(self):
        self.session.request.return_value = response({"nextPageToken": "repeat"})
        with self.assertRaises(CalendarAPIError):
            self.service.list_events(start_time=self.start, end_time=self.end)
        self.assertEqual(self.session.request.call_count, 2)

    def test_calendar_and_event_ids_are_url_encoded(self):
        self.session.request.return_value = response(self.existing())
        self.service.get_event("event/a?b", calendar_id="name@example.com")
        url = self.session.request.call_args.args[1]
        self.assertIn("/name%40example.com/events/event%2Fa%3Fb", url)

    def test_create_returns_external_id_and_category_metadata(self):
        def create(method, url, **kwargs):
            self.assertEqual(method, "POST")
            return response({**kwargs["json"], "etag": '"one"'})
        self.session.request.side_effect = create
        result = self.service.execute(self.action)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.external_id, result.event["id"])
        self.assertEqual(len(result.external_id), 64)
        body = self.session.request.call_args.kwargs["json"]
        self.assertEqual(body["summary"], "Study Java")
        self.assertEqual(body["start"]["dateTime"], self.start.isoformat())
        self.assertEqual(body["extendedProperties"]["private"]["timeslice_category"], "academics")
        self.assertNotIn("attendees", body)
        self.assertEqual(self.session.request.call_args.kwargs["timeout"], 30)

    def test_create_retry_recovers_matching_existing_event(self):
        saved = {}
        def request(method, url, **kwargs):
            if method == "POST" and not saved:
                saved.update(kwargs["json"])
                return response(saved.copy())
            return response(status=409) if method == "POST" else response(saved.copy())
        self.session.request.side_effect = request
        first = self.service.execute(self.action)
        second = self.service.execute(self.action)
        self.assertEqual(first.external_id, second.external_id)

    def test_action_id_reuse_with_different_payload_rejected(self):
        saved = {}
        def request(method, url, **kwargs):
            if method == "POST" and not saved:
                saved.update(kwargs["json"])
                return response(saved.copy())
            return response(status=409) if method == "POST" else response(saved.copy())
        self.session.request.side_effect = request
        self.service.execute(self.action)
        with self.assertRaises(CalendarConflictError):
            self.service.execute(replace(self.action, event=replace(self.event, title="Different event")))

    def test_update_uses_etag_and_preserves_private_metadata(self):
        current = self.existing(extendedProperties={"private": {"another_app": "keep"}})
        self.session.request.side_effect = [response(current), response({"id": "google-event"})]
        result = self.service.execute(replace(
            self.action, operation="update", event_id="google-event", expected_etag='"version-one"'
        ))
        self.assertEqual(result.external_id, "google-event")
        method = self.session.request.call_args.args[0]
        kwargs = self.session.request.call_args.kwargs
        self.assertEqual(method, "PATCH")
        self.assertEqual(kwargs["headers"]["If-Match"], '"version-one"')
        self.assertEqual(kwargs["json"]["extendedProperties"]["private"]["another_app"], "keep")
        self.assertNotIn("attendees", kwargs["json"])

    def test_changed_event_is_not_updated(self):
        self.session.request.return_value = response(self.existing(etag='"changed"'))
        with self.assertRaises(CalendarConflictError):
            self.service.execute(replace(
                self.action, operation="update", event_id="google-event", expected_etag='"version-one"'
            ))
        self.assertEqual(self.session.request.call_count, 1)

    def test_recurring_or_shared_events_are_not_modified(self):
        for change in ({"recurrence": ["RRULE:FREQ=DAILY"]},
                       {"recurringEventId": "parent"}, {"attendees": [{"email": "person@example.com"}]}):
            self.session.request.reset_mock()
            self.session.request.return_value = response(self.existing(**change))
            with self.subTest(change=change), self.assertRaises(CalendarValidationError):
                self.service.execute(replace(
                    self.action, operation="delete", event=None, event_id="google-event",
                    expected_etag='"version-one"'
                ))
            self.assertEqual(self.session.request.call_count, 1)

    def test_delete_uses_conditional_request_and_returns_id(self):
        self.session.request.side_effect = [response(self.existing()), response(status=204)]
        result = self.service.execute(replace(
            self.action, operation="delete", event=None, event_id="google-event",
            expected_etag='"version-one"'
        ))
        self.assertEqual(result.external_id, "google-event")
        self.assertEqual(self.session.request.call_args.args[0], "DELETE")
        self.assertEqual(self.session.request.call_args.kwargs["headers"]["If-Match"], '"version-one"')

    def test_provider_errors_are_sanitized(self):
        for status in (403, 404, 410, 429, 500):
            self.session.request.return_value = response({"secret": "provider-payload"}, status)
            with self.subTest(status=status), self.assertRaises(CalendarAPIError) as caught:
                self.service.get_event("google-event")
            self.assertEqual(caught.exception.status_code, status)
            self.assertNotIn("provider-payload", str(caught.exception))

    def test_unauthorized_and_transport_auth_failure_require_reconnect(self):
        self.session.request.return_value = response(status=401)
        with self.assertRaises(GoogleReconnectRequired):
            self.service.get_event("google-event")
        self.session.request.side_effect = RefreshError("secret-token")
        with self.assertRaises(GoogleReconnectRequired) as caught:
            self.service.get_event("google-event")
        self.assertNotIn("secret-token", str(caught.exception))

    def test_network_errors_are_sanitized(self):
        self.session.request.side_effect = ConnectionError("secret-token")
        with self.assertRaises(CalendarAPIError) as caught:
            self.service.execute(self.action)
        self.assertIn("check sync status", str(caught.exception))
        self.assertNotIn("secret-token", str(caught.exception))

    def test_conditional_write_failure(self):
        self.session.request.side_effect = [response(self.existing()), response(status=412)]
        with self.assertRaises(CalendarConflictError) as caught:
            self.service.execute(replace(
                self.action, operation="delete", event=None, event_id="google-event",
                expected_etag='"version-one"'
            ))
        self.assertEqual(caught.exception.status_code, 412)

    def test_malformed_response_rejected(self):
        self.session.request.return_value = response(["not-an-object"])
        with self.assertRaises(CalendarAPIError):
            self.service.get_event("google-event")

    def test_close_releases_transport(self):
        self.service.close()
        self.session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
