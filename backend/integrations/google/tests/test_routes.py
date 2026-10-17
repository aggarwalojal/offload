"""Local HTTP connection flow with Google token/API calls mocked."""

from datetime import datetime, timezone
import re
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from google_auth_oauthlib.flow import Flow

from backend.integrations.google.config import GoogleConfig, GoogleConfigError
from backend.integrations.google.demo_app import create_demo_app
from backend.integrations.google.oauth import GoogleReconnectRequired


class ConnectionRoutesTests(unittest.TestCase):
    def setUp(self):
        self.config = GoogleConfig(client_id="test-client", client_secret="test-secret")
        self.app = create_demo_app(self.config)
        self.client = TestClient(self.app, base_url="http://localhost:8000")
        self.addCleanup(self.client.close)

    def connect(self, client=None):
        client = client or self.client
        page = client.get("/")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        result = client.post("/api/google/connect", data={"csrf": csrf},
                             headers={"Origin": "http://localhost:8000"}, follow_redirects=False)
        self.assertEqual(result.status_code, 303)
        return parse_qs(urlsplit(result.headers["location"]).query)["state"][0]

    def exchange(self, flow, **kwargs):
        flow.oauth2session.token = {
            "access_token": "private-access-token",
            "refresh_token": "private-refresh-token",
            "token_type": "Bearer",
            "expires_at": datetime.now(timezone.utc).timestamp() + 3600,
            "scope": list(self.config.scopes),
        }

    def finish(self, state, client=None):
        with patch.object(Flow, "fetch_token", autospec=True, side_effect=self.exchange):
            return (client or self.client).get(
                "/api/google/callback", params={"state": state, "code": "private-auth-code"},
                follow_redirects=False,
            )

    def test_connection_page_sets_private_browser_session(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Connect Google Calendar", response.text)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "same-origin")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertNotIn("test-secret", response.text)

    def test_connect_requires_session_and_csrf(self):
        self.assertEqual(self.client.post("/api/google/connect").status_code, 401)
        self.client.get("/")
        self.assertEqual(self.client.post("/api/google/connect", data={"csrf": "wrong"},
                         headers={"Origin": "http://localhost:8000"}).status_code, 403)
        self.assertEqual(self.client.post("/api/google/connect", data={"csrf": "wrong"},
                         headers={"Origin": "https://attacker.example"}).status_code, 403)

    def test_successful_connection_stores_credentials_server_side(self):
        state = self.connect()
        result = self.finish(state)
        self.assertEqual(result.status_code, 303)
        self.assertEqual(result.headers["location"], "/google/connected")
        self.assertEqual(result.headers["referrer-policy"], "no-referrer")
        page = self.client.get("/google/connected")
        self.assertIn("Your calendar is ready", page.text)
        status = self.client.get("/api/google/status")
        self.assertTrue(status.json()["connected"])
        for secret in ("private-access-token", "private-refresh-token", "test-secret"):
            self.assertNotIn(secret, page.text + status.text + result.text)

    def test_callback_requires_original_browser(self):
        state = self.connect()
        with TestClient(self.app, base_url="http://localhost:8000") as other:
            other.get("/")
            result = self.finish(state, client=other)
            self.assertEqual(result.status_code, 400)
        self.assertEqual(self.finish(state).status_code, 303)

    def test_callback_replay_is_rejected(self):
        state = self.connect()
        self.assertEqual(self.finish(state).status_code, 303)
        self.assertEqual(self.finish(state).status_code, 400)

    def test_duplicate_callback_parameters_rejected(self):
        state = self.connect()
        result = self.client.get("/api/google/callback", params=[("state", state), ("state", state), ("code", "code")])
        self.assertEqual(result.status_code, 400)

    def test_denied_consent_has_no_connection(self):
        state = self.connect()
        result = self.client.get("/api/google/callback", params={"state": state, "error": "access_denied"})
        self.assertEqual(result.status_code, 400)
        self.assertFalse(self.client.get("/api/google/status").json()["connected"])

    def test_events_require_connection(self):
        self.client.get("/")
        result = self.client.get("/api/google/events")
        self.assertEqual(result.status_code, 401)

    def test_events_are_projected_without_private_metadata(self):
        self.finish(self.connect())
        event = {"id": "event-one", "summary": "Study Java", "start": {"dateTime": "2026-10-18T09:00:00-04:00"},
                 "end": {"dateTime": "2026-10-18T11:00:00-04:00"}, "status": "confirmed",
                 "extendedProperties": {"private": {"secret": "private-metadata"}}}
        with patch("backend.integrations.google.routes.GoogleCalendarService") as calendar:
            calendar.return_value.list_events.return_value = [event]
            result = self.client.get("/api/google/events")
            calendar.return_value.close.assert_called_once()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["events"][0]["external_id"], "event-one")
        self.assertNotIn("private-metadata", result.text)

    def test_expired_access_returns_reconnect(self):
        self.finish(self.connect())
        with patch("backend.integrations.google.routes.GoogleCalendarService") as calendar:
            calendar.return_value.list_events.side_effect = GoogleReconnectRequired("Please reconnect.")
            self.assertEqual(self.client.get("/api/google/events").status_code, 401)
            calendar.return_value.close.assert_called_once()

    def test_unconnected_browser_cannot_read_another_users_events(self):
        self.finish(self.connect())
        with TestClient(self.app, base_url="http://localhost:8000") as other:
            other.get("/")
            self.assertFalse(other.get("/api/google/status").json()["connected"])
            self.assertEqual(other.get("/api/google/events").status_code, 401)

    def test_remote_hosts_and_remote_peer_rejected(self):
        self.assertEqual(self.client.get("/", headers={"host": "attacker.example"}).status_code, 400)
        with TestClient(self.app, base_url="http://localhost:8000", client=("203.0.113.1", 1234)) as remote:
            self.assertEqual(remote.get("/").status_code, 403)

    def test_demo_rejects_unconfigured_credentials(self):
        with self.assertRaises(GoogleConfigError):
            create_demo_app(GoogleConfig(client_id="replace-with-client-id", client_secret="replace-with-secret"))

    def test_demo_refuses_production_callback(self):
        with self.assertRaises(GoogleConfigError):
            create_demo_app(GoogleConfig(client_id="test", client_secret="test",
                                         redirect_uri="https://example.com/api/google/callback"))


if __name__ == "__main__":
    unittest.main()
