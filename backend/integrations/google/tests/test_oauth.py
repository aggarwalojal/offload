"""Offline OAuth behavior tests using real Google clients and mocked transport."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from requests.exceptions import ConnectionError

from backend.integrations.google.config import GOOGLE_TOKEN_URI, GoogleConfig
from backend.integrations.google.oauth import (
    GoogleConsentDenied,
    GoogleOAuthError,
    GoogleOAuthService,
    GoogleReconnectRequired,
    InvalidOAuthState,
)

MODULE = "backend.integrations.google.oauth"


class GoogleOAuthTests(unittest.TestCase):
    def setUp(self):
        self.config = GoogleConfig(client_id="test-client", client_secret="test-secret")
        self.service = GoogleOAuthService(self.config)
        self.user = {"user_id": "user-one", "session_id": "opaque-browser-session"}

    def begin(self):
        url = self.service.begin_authorization(**self.user)
        return url, parse_qs(urlsplit(url).query)["state"][0]

    def credentials(self, *, expired=False, refresh_token="test-refresh", scopes=None):
        return Credentials(
            token="test-access",
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            scopes=self.config.scopes if scopes is None else scopes,
            expiry=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(hours=-1 if expired else 1),
        )

    def token_response(self, flow, **kwargs):
        flow.oauth2session.token = {
            "access_token": "test-access",
            "refresh_token": "test-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
            "expires_at": datetime.now(timezone.utc).timestamp() + 3600,
            "scope": " ".join(self.config.scopes),
        }

    def test_authorization_url_has_scopes_offline_consent_and_pkce(self):
        url, state = self.begin()
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(urlsplit(url).hostname, "accounts.google.com")
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["prompt"], ["consent"])
        self.assertEqual(query["redirect_uri"], [self.config.redirect_uri])
        self.assertEqual(set(query["scope"][0].split()), set(self.config.scopes))
        self.assertEqual(query["code_challenge_method"], ["S256"])
        verifier = self.service._pending[state].flow.code_verifier
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        self.assertEqual(query["code_challenge"], [challenge.decode().rstrip("=")])
        self.assertNotIn(self.config.client_secret, url)
        self.assertNotIn(verifier, url)

    def test_state_is_unique(self):
        self.assertNotEqual(self.begin()[1], self.begin()[1])

    def test_successful_exchange_and_replay_prevention(self):
        _, state = self.begin()
        with patch(f"{MODULE}.Flow.fetch_token", autospec=True,
                   side_effect=self.token_response) as fetch:
            credentials = self.service.complete_authorization(
                **self.user, state=state, code="test-code"
            )
            self.assertEqual(credentials.token, "test-access")
            self.assertEqual(credentials.refresh_token, "test-refresh")
            self.assertEqual(fetch.call_args.kwargs, {"code": "test-code", "timeout": 30})
            with self.assertRaises(InvalidOAuthState):
                self.service.complete_authorization(**self.user, state=state, code="test-code")
            self.assertEqual(fetch.call_count, 1)

    def test_unknown_state_does_not_contact_google(self):
        with patch(f"{MODULE}.Flow.fetch_token") as fetch:
            with self.assertRaises(InvalidOAuthState):
                self.service.complete_authorization(**self.user, state="unknown", code="code")
            fetch.assert_not_called()

    def test_wrong_user_or_browser_cannot_consume_flow(self):
        _, state = self.begin()
        for user in ({**self.user, "user_id": "other-user"},
                     {**self.user, "session_id": "other-browser"}):
            with self.subTest(user=user), patch(f"{MODULE}.Flow.fetch_token") as fetch:
                with self.assertRaises(InvalidOAuthState):
                    self.service.complete_authorization(**user, state=state, code="code")
                fetch.assert_not_called()
        self.assertIn(state, self.service._pending)

    def test_expired_state_rejected(self):
        with patch(f"{MODULE}.monotonic", return_value=0):
            _, state = self.begin()
        with patch(f"{MODULE}.monotonic", return_value=600):
            with self.assertRaises(InvalidOAuthState):
                self.service.complete_authorization(**self.user, state=state, code="code")
        self.assertNotIn(state, self.service._pending)

    def test_denial_consumes_state_without_exchange(self):
        _, state = self.begin()
        with patch(f"{MODULE}.Flow.fetch_token") as fetch:
            with self.assertRaises(GoogleConsentDenied):
                self.service.complete_authorization(
                    **self.user, state=state, error="access_denied"
                )
            fetch.assert_not_called()
        self.assertNotIn(state, self.service._pending)

    def test_missing_code_and_provider_errors_are_safe(self):
        for args in ({}, {"error": "provider-secret-error"}):
            _, state = self.begin()
            with self.subTest(args=args):
                with self.assertRaises(GoogleOAuthError) as caught:
                    self.service.complete_authorization(**self.user, state=state, **args)
                self.assertNotIn("provider-secret-error", str(caught.exception))
                self.assertNotIn(state, self.service._pending)

    def test_exchange_failure_is_sanitized_and_consumes_state(self):
        _, state = self.begin()
        with patch(f"{MODULE}.Flow.fetch_token", side_effect=ConnectionError("secret-token")):
            with self.assertRaises(GoogleOAuthError) as caught:
                self.service.complete_authorization(**self.user, state=state, code="code")
        self.assertNotIn("secret-token", str(caught.exception))
        self.assertNotIn(state, self.service._pending)

    def test_partial_consent_rejected(self):
        _, state = self.begin()
        partial = self.credentials(scopes=self.config.scopes[:1])
        with patch(f"{MODULE}.Flow.fetch_token"), patch(
            f"{MODULE}.Flow.credentials", new_callable=unittest.mock.PropertyMock,
            return_value=partial,
        ):
            with self.assertRaises(GoogleReconnectRequired):
                self.service.complete_authorization(**self.user, state=state, code="code")

    def test_missing_refresh_token_requires_reconnect(self):
        _, state = self.begin()
        credentials = self.credentials(refresh_token=None)
        with patch(f"{MODULE}.Flow.fetch_token"), patch(
            f"{MODULE}.Flow.credentials", new_callable=unittest.mock.PropertyMock,
            return_value=credentials,
        ):
            with self.assertRaises(GoogleReconnectRequired):
                self.service.complete_authorization(**self.user, state=state, code="code")

    def test_valid_credentials_do_not_refresh(self):
        credentials = self.credentials()
        with patch.object(Credentials, "refresh") as refresh:
            self.assertIs(self.service.refresh_credentials(credentials), credentials)
            refresh.assert_not_called()

    def test_expired_credentials_refresh(self):
        credentials = self.credentials(expired=True)
        def refresh(request):
            credentials.token = "new-access"
            credentials.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        with patch.object(Credentials, "refresh", side_effect=refresh) as mocked:
            self.assertIs(self.service.refresh_credentials(credentials), credentials)
            mocked.assert_called_once()
        self.assertEqual(credentials.token, "new-access")
        self.assertEqual(credentials.refresh_token, "test-refresh")

    def test_refresh_failure_requires_reconnect_without_leaking(self):
        credentials = self.credentials(expired=True)
        with patch.object(Credentials, "refresh", side_effect=RefreshError("secret-token")):
            with self.assertRaises(GoogleReconnectRequired) as caught:
                self.service.refresh_credentials(credentials)
        self.assertNotIn("secret-token", str(caught.exception))

    def test_expired_credentials_without_refresh_token(self):
        with self.assertRaises(GoogleReconnectRequired):
            self.service.refresh_credentials(self.credentials(expired=True, refresh_token=None))

    def test_untrusted_token_endpoint_rejected(self):
        credentials = self.credentials(expired=True)
        credentials._token_uri = "https://attacker.example/token"
        with patch.object(Credentials, "refresh") as refresh:
            with self.assertRaises(GoogleReconnectRequired):
                self.service.refresh_credentials(credentials)
            refresh.assert_not_called()

    def test_required_user_and_session(self):
        for user in ({**self.user, "user_id": ""}, {**self.user, "session_id": ""}):
            with self.subTest(user=user), self.assertRaises(GoogleOAuthError):
                self.service.begin_authorization(**user)


if __name__ == "__main__":
    unittest.main()
