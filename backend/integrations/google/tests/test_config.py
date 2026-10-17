"""Run: python3 -m unittest discover -s backend/integrations/google/tests -v"""

import unittest

from backend.integrations.google.config import (
    CALENDAR_SCOPES,
    TASKS_SCOPES,
    GoogleConfigError,
    get_google_config,
)


class GoogleConfigTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "GOOGLE_CLIENT_ID": "test-client",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }

    def test_calendar_only_by_default(self):
        config = get_google_config(self.env)
        self.assertEqual(config.scopes, CALENDAR_SCOPES)
        self.assertEqual(config.redirect_uri, "http://localhost:8000/api/google/callback")

    def test_tasks_are_opt_in(self):
        self.env["GOOGLE_ENABLE_TASKS"] = "true"
        self.assertEqual(get_google_config(self.env).scopes, CALENDAR_SCOPES + TASKS_SCOPES)

    def test_credentials_required(self):
        for key in self.env:
            with self.subTest(key=key):
                with self.assertRaisesRegex(GoogleConfigError, key):
                    get_google_config({**self.env, key: "  "})

    def test_invalid_boolean_rejected(self):
        with self.assertRaises(GoogleConfigError):
            get_google_config({**self.env, "GOOGLE_ENABLE_TASKS": "yes"})

    def test_reject_unsafe_redirects(self):
        for uri in (
            "http://example.com/callback", "ftp://localhost/callback",
            "https://user:password@example.com/callback", "https://example.com/#token",
            "https://example.com/?token=secret", "https://example.com:bad/callback",
            "not-a-url", "http://localhost.evil.com/callback", "",
        ):
            with self.subTest(uri=uri):
                with self.assertRaises(GoogleConfigError):
                    get_google_config({**self.env, "GOOGLE_REDIRECT_URI": uri})

    def test_allow_https_and_local_redirects(self):
        for uri in ("https://timeslice.example/api/google/callback",
                    "http://127.0.0.1:8000/api/google/callback",
                    "http://[::1]:8000/api/google/callback"):
            with self.subTest(uri=uri):
                self.assertEqual(
                    get_google_config({**self.env, "GOOGLE_REDIRECT_URI": uri}).redirect_uri,
                    uri,
                )

    def test_repr_does_not_expose_credentials(self):
        representation = repr(get_google_config(self.env))
        self.assertNotIn("test-secret", representation)
        self.assertNotIn("test-client", representation)

    def test_oauth_client_config(self):
        config = get_google_config(self.env)
        web = config.oauth_client_config()["web"]
        self.assertEqual(web["client_id"], "test-client")
        self.assertEqual(web["client_secret"], "test-secret")
        self.assertEqual(web["redirect_uris"], [config.redirect_uri])


if __name__ == "__main__":
    unittest.main()
