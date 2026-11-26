"""Unit tests for SSO authentication providers, session management, and regulatory compliance."""

import base64
import hashlib
import json
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from process_toolkit.sso.compliance import (
    COOKIE_CATEGORIES,
    MINIMAL_SCOPES,
    get_notice_at_collection,
    get_privacy_policy_text,
    get_terms_of_service_text,
)
from process_toolkit.sso.providers import (
    GitHubProvider,
    GoogleProvider,
    MicrosoftProvider,
    OutlookProvider,
    generate_oauth_state,
    generate_pkce_pair,
    get_configured_providers,
    get_providers_metadata,
)
from process_toolkit.sso.session_manager import SSOSessionManager


class TestPKCEAndState(unittest.TestCase):
    """Tests RFC 7636 PKCE code generation and cryptographic state tokens."""

    def test_generate_pkce_pair(self):
        verifier, challenge = generate_pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)

        # Verify challenge is SHA-256 hash of verifier, base64url encoded
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).decode("ascii").rstrip("=")
        self.assertEqual(challenge, expected_challenge)

    def test_generate_oauth_state(self):
        state1 = generate_oauth_state()
        state2 = generate_oauth_state()
        self.assertNotEqual(state1, state2)
        self.assertGreaterEqual(len(state1), 32)


class TestSSOProviders(unittest.TestCase):
    """Tests Google, GitHub, Microsoft, and Outlook SSO provider implementations."""

    def test_provider_definitions(self):
        providers = get_configured_providers()
        self.assertIn("google", providers)
        self.assertIn("github", providers)
        self.assertIn("microsoft", providers)
        self.assertIn("outlook", providers)

        google = providers["google"]
        github = providers["github"]
        microsoft = providers["microsoft"]
        outlook = providers["outlook"]

        self.assertEqual(google.display_name, "Google")
        self.assertEqual(github.display_name, "GitHub")
        self.assertEqual(microsoft.display_name, "Microsoft")
        self.assertEqual(outlook.display_name, "Outlook")

        # Verify data minimization minimal scopes
        self.assertIn("email", google.scopes)
        self.assertIn("user:email", github.scopes)
        self.assertIn("email", microsoft.scopes)
        self.assertIn("email", outlook.scopes)

    def test_authorization_url_generation(self):
        providers = get_configured_providers()
        google = providers["google"]
        state = "test-state-12345"
        _, challenge = generate_pkce_pair()
        redirect_uri = "http://127.0.0.1:8081/auth/callback/google"

        google.client_id = "test-client-id"
        google.client_secret = "test-client-secret"
        url_real = google.get_authorization_url(redirect_uri, state, code_challenge=challenge)
        self.assertIn("accounts.google.com", url_real)
        self.assertIn("client_id=test-client-id", url_real)
        self.assertIn("code_challenge=", url_real)
        self.assertIn("code_challenge_method=S256", url_real)
        self.assertIn("prompt=login", url_real)

    def test_verify_token(self):
        providers = get_configured_providers()
        github = providers["github"]
        with patch.object(github, "fetch_user_profile", return_value={"id": 519524, "login": "tpayne", "name": "Tim Payne", "email": "tpayne@example.com", "avatar_url": "https://avatars.githubusercontent.com/u/519524"}):
            profile = github.verify_token("gho_test_token")
            self.assertEqual(profile["provider"], "github")
            self.assertEqual(profile["id"], "519524")
            self.assertEqual(profile["username"], "tpayne")
            self.assertEqual(profile["name"], "Tim Payne")
            self.assertEqual(profile["email"], "tpayne@example.com")


class TestSSOSessionManager(unittest.TestCase):
    """Tests session creation, token retrieval, GDPR export, and erasure."""

    def setUp(self):
        self.temp_file = tempfile.mktemp(suffix=".json")
        self.manager = SSOSessionManager(persistence_file=self.temp_file)

    def tearDown(self):
        if os.path.exists(self.temp_file):
            try:
                os.remove(self.temp_file)
            except Exception:
                pass

    def test_create_and_get_session(self):
        profile = {
            "id": "user-123",
            "name": "Jane Doe",
            "email": "jane@example.com",
            "provider": "google",
        }
        sess = self.manager.create_session(profile)
        token = sess["token"]
        self.assertTrue(token.startswith("sso_"))

        retrieved = self.manager.get_session(token)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["user"]["email"], "jane@example.com")

    def test_revoke_session(self):
        profile = {"id": "user-456", "name": "John Doe", "email": "john@example.com", "provider": "github"}
        sess = self.manager.create_session(profile)
        token = sess["token"]

        self.assertTrue(self.manager.revoke_session(token))
        self.assertIsNone(self.manager.get_session(token))

    def test_gdpr_export_data(self):
        profile = {"id": "user-789", "name": "Alice User", "email": "alice@example.com", "provider": "microsoft"}
        sess = self.manager.create_session(profile)
        token = sess["token"]
        self.manager.link_chat_session(token, "chat-session-001")

        export_data = self.manager.export_user_data(token)
        self.assertIn("user_profile", export_data)
        self.assertEqual(export_data["user_profile"]["name"], "Alice User")
        self.assertIn("GDPR Article 15", export_data["statement"])
        self.assertIn("chat-session-001", export_data["session_history"][0]["linked_chat_sessions"])

    def test_persistence_file_is_not_world_or_group_readable(self):
        # CONFIRMED AS A REAL BUG: every live session's own bearer token
        # is a password-equivalent credential, but this file (holding
        # EVERY user's tokens at once) was written with no permission
        # restriction -- inheriting the default umask, typically
        # world-readable. cli_auth.py's own credentials.json already
        # protected itself with chmod 0600; this file needed the same.
        self.manager.create_session({"id": "perm-check", "name": "P", "email": "p@example.com", "provider": "google"})
        mode = stat.S_IMODE(os.stat(self.temp_file).st_mode)
        self.assertEqual(mode, 0o600)

    def test_delete_user_data_does_not_hold_the_lock_during_filesystem_purge(self):
        # CONFIRMED AS A REAL BUG: purge_session (shutil.rmtree -- real
        # filesystem I/O) used to run INSIDE the manager's own lock,
        # blocking every other user's own session lookups/creation for
        # as long as that took.
        profile = {"id": "user-lock-check", "name": "Lock Check", "email": "lock@example.com", "provider": "google"}
        sess = self.manager.create_session(profile)
        token = sess["token"]
        self.manager.link_chat_session(token, "some-chat-session-id")

        lock_was_free = []

        def fake_purge_session(session_id):
            acquired = self.manager._lock.acquire(blocking=False)
            lock_was_free.append(acquired)
            if acquired:
                self.manager._lock.release()
            return False

        with patch("process_toolkit.sso.session_manager.purge_session", side_effect=fake_purge_session):
            self.manager.delete_user_data(token)

        self.assertEqual(lock_was_free, [True])

    def test_gdpr_delete_data(self):
        profile = {"id": "user-erasure", "name": "Bob User", "email": "bob@example.com", "provider": "outlook"}
        sess = self.manager.create_session(profile)
        token = sess["token"]

        deletion_result = self.manager.delete_user_data(token)
        self.assertEqual(deletion_result["status"], "ok")
        self.assertIn("Right to Erasure", deletion_result["action"])
        self.assertEqual(deletion_result["deleted_email"], "bob@example.com")

        # Confirm session is gone
        self.assertIsNone(self.manager.get_session(token))


class TestRegulatoryCompliance(unittest.TestCase):
    """Tests compliance notices, policies, and cookie specifications."""

    def test_notice_at_collection(self):
        notice = get_notice_at_collection()
        self.assertIn("Notice at Collection", notice["title"])
        self.assertIn("do_not_sell", notice)
        self.assertIn("user_rights", notice)
        self.assertIn("subprocessors", notice)

    def test_cookie_categories(self):
        self.assertIn("strictly_necessary", COOKIE_CATEGORIES)
        self.assertTrue(COOKIE_CATEGORIES["strictly_necessary"]["required"])
        self.assertIn("preferences", COOKIE_CATEGORIES)
        self.assertFalse(COOKIE_CATEGORIES["preferences"]["required"])

    def test_disclosed_cookie_names_match_the_cookies_cli_py_actually_sets(self):
        # CONFIRMED AS A REAL BUG: this disclosure listed "sso_code_verifier"
        # while cli.py/agent.py actually set "sso_pkce_verifier" -- a GDPR
        # Art. 13/14 Notice at Collection naming a cookie that doesn't
        # exist, while staying silent about the one that actually does.
        disclosed_names = {
            c["name"] for cat in COOKIE_CATEGORIES.values() for c in cat["cookies"]
        }
        self.assertIn("sso_pkce_verifier", disclosed_names)
        self.assertNotIn("sso_code_verifier", disclosed_names)

    def test_privacy_policy_text(self):
        policy = get_privacy_policy_text()
        self.assertIn("Privacy Policy", policy)
        self.assertIn("GDPR", policy)
        self.assertIn("CCPA", policy)
        self.assertIn("Right to Erasure", policy)

    def test_terms_of_service_text(self):
        terms = get_terms_of_service_text()
        self.assertIn("Terms of Service", terms)
        self.assertIn("Acceptable Use", terms)


if __name__ == "__main__":
    unittest.main()
