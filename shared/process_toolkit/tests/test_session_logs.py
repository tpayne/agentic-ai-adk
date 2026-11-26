"""Tests for session-scoped server logging with automatic credential redaction."""

import logging
import os
import tempfile
import unittest
from unittest.mock import patch

from process_toolkit import paths
from process_toolkit.session_logs import (
    SessionLogHandler,
    clear_session_logs,
    get_session_log_entries,
    install_session_log_handler,
    record_session_log,
    redact_sensitive_data,
)


class TestSensitiveDataRedaction(unittest.TestCase):
    """Tests that credentials, tokens, and secrets are properly redacted."""

    def test_redact_google_api_key(self):
        text = "Calling model with key AIzaSyD-1234567890abcdefghijklmnopqrstuv"
        clean = redact_sensitive_data(text)
        self.assertNotIn("AIzaSyD", clean)
        self.assertIn("[REDACTED_API_KEY]", clean)

    def test_redact_openai_style_key(self):
        text = "Using OpenAI key sk-abcdef12345678901234567890 for embeddings"
        clean = redact_sensitive_data(text)
        self.assertNotIn("sk-abcdef", clean)
        self.assertIn("[REDACTED_API_KEY]", clean)

    def test_redact_bearer_token(self):
        text = "HTTP header Authorization: Bearer secret_jwt_token_12345678.abc.xyz"
        clean = redact_sensitive_data(text)
        self.assertNotIn("secret_jwt_token", clean)
        self.assertIn("Bearer [REDACTED_TOKEN]", clean)

    def test_redact_basic_auth(self):
        text = "Header Authorization: Basic dXNlcjpwYXNzd29yZDEyMw=="
        clean = redact_sensitive_data(text)
        self.assertNotIn("dXNlcjpwYXNzd29yZDEyMw==", clean)
        self.assertIn("Basic [REDACTED_AUTH]", clean)

    def test_redact_key_value_pairs(self):
        text = "Config loaded: api_key='supersecret123', password=\"dbpass999\", token=xyz12345"
        clean = redact_sensitive_data(text)
        self.assertNotIn("supersecret123", clean)
        self.assertNotIn("dbpass999", clean)
        self.assertNotIn("xyz12345", clean)
        self.assertIn("api_key=[REDACTED]", clean)
        self.assertIn("password=[REDACTED]", clean)
        self.assertIn("token=[REDACTED]", clean)

    def test_redact_url_query_parameters(self):
        text = "GET /api?api_key=mysecretkey123&other=val"
        clean = redact_sensitive_data(text)
        self.assertNotIn("mysecretkey123", clean)
        self.assertIn("api_key=[REDACTED]", clean)

    def test_redact_environment_secret_values(self):
        with patch.dict(os.environ, {"WEBAPIKEY": "my-ultra-secret-web-key", "GEMINI_API_KEY": "gemini-secret-val-987"}):
            text = "User authenticated with key my-ultra-secret-web-key and engine gemini-secret-val-987"
            clean = redact_sensitive_data(text)
            self.assertNotIn("my-ultra-secret-web-key", clean)
            self.assertNotIn("gemini-secret-val-987", clean)
            self.assertIn("[REDACTED_API_KEY]", clean)


class TestSessionLogHandler(unittest.TestCase):
    """Tests the SessionLogHandler in-memory buffer, file persistence, and querying."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.handler = SessionLogHandler(max_entries_per_session=100)

    def test_record_and_get_entries(self):
        sid = "test-session-12345678"
        self.handler.record_entry(sid, "INFO", "First turn completed")
        self.handler.record_entry(sid, "WARNING", "Token limit approaching")
        self.handler.record_entry(sid, "ERROR", "Failed to contact backend API: AIzaSyD-1234567890abcdefghijklmnopqrstuv")

        # Query all
        res_all = self.handler.get_entries(sid, level="all")
        self.assertEqual(res_all["total_count"], 3)
        self.assertEqual(len(res_all["logs"]), 3)
        # Verify redaction in captured log
        self.assertNotIn("AIzaSyD", res_all["logs"][2]["message"])
        self.assertIn("[REDACTED_API_KEY]", res_all["logs"][2]["message"])

        # Query by level
        res_err = self.handler.get_entries(sid, level="error")
        self.assertEqual(len(res_err["logs"]), 1)
        self.assertEqual(res_err["logs"][0]["level"], "ERROR")

        res_warn = self.handler.get_entries(sid, level="warning")
        self.assertEqual(len(res_warn["logs"]), 1)
        self.assertEqual(res_warn["logs"][0]["level"], "WARNING")

        res_info = self.handler.get_entries(sid, level="info")
        self.assertEqual(len(res_info["logs"]), 1)
        self.assertEqual(res_info["logs"][0]["level"], "INFO")

        # Query by search
        res_search = self.handler.get_entries(sid, search="limit")
        self.assertEqual(len(res_search["logs"]), 1)
        self.assertIn("limit approaching", res_search["logs"][0]["message"])

    def test_session_isolation(self):
        sid1 = "session-aaa-12345678"
        sid2 = "session-bbb-12345678"

        self.handler.record_entry(sid1, "INFO", "Session 1 confidential data")
        self.handler.record_entry(sid2, "INFO", "Session 2 distinct log")

        logs1 = self.handler.get_entries(sid1)["logs"]
        logs2 = self.handler.get_entries(sid2)["logs"]

        self.assertEqual(len(logs1), 1)
        self.assertIn("Session 1", logs1[0]["message"])
        self.assertNotIn("Session 2", logs1[0]["message"])

        self.assertEqual(len(logs2), 1)
        self.assertIn("Session 2", logs2[0]["message"])
        self.assertNotIn("Session 1", logs2[0]["message"])

    def test_emit_with_paths_use_session(self):
        sid = "session-ctx-12345678"
        logger = logging.getLogger("TestSessionLogger")
        logger.setLevel(logging.INFO)
        logger.addHandler(self.handler)

        with paths.use_session(sid):
            logger.info("Message inside session context")
            logger.warning("Warning with password=supersecretpass")

        entries = self.handler.get_entries(sid)["logs"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["message"], "Message inside session context")
        self.assertNotIn("supersecretpass", entries[1]["message"])
        self.assertIn("password=[REDACTED]", entries[1]["message"])

        logger.removeHandler(self.handler)

    def test_exception_log_entries_do_not_duplicate_the_message(self):
        # CONFIRMED AS A REAL BUG: emit() used to set record.exc_text from
        # self.format(record), which bakes record.getMessage() into its
        # own output (Python's default Formatter always does) -- so the
        # message ended up concatenated onto itself, in front of the
        # traceback, on every exception-logged entry.
        sid = "session-exc-dup-12345678"
        logger = logging.getLogger("TestExcLogger")
        logger.setLevel(logging.INFO)
        logger.addHandler(self.handler)

        with paths.use_session(sid):
            try:
                raise ValueError("boom, something broke")
            except ValueError:
                logger.exception("Failed while processing turn")

        entries = self.handler.get_entries(sid)["logs"]
        self.assertEqual(len(entries), 1)
        message = entries[0]["message"]
        self.assertEqual(message.count("Failed while processing turn"), 1)
        self.assertIn("Traceback (most recent call last):", message)
        self.assertIn("ValueError: boom, something broke", message)

        logger.removeHandler(self.handler)

    def test_get_entries_limit_zero_returns_no_logs(self):
        # CONFIRMED AS A REAL BUG: `if limit and limit > 0` treated 0 as
        # falsy and skipped limiting entirely, returning everything -- and
        # even a naive fix (`filtered[-limit:]`) would have been wrong too,
        # since Python slicing treats -0 the same as 0.
        sid = "session-limit-zero-12345678"
        self.handler.record_entry(sid, "INFO", "one")
        self.handler.record_entry(sid, "INFO", "two")

        res = self.handler.get_entries(sid, limit=0)
        self.assertEqual(res["total_count"], 2)
        self.assertEqual(res["logs"], [])

    def test_clear_session(self):
        sid = "session-to-clear-12345678"
        self.handler.record_entry(sid, "INFO", "Entry before clear")
        self.assertEqual(len(self.handler.get_entries(sid)["logs"]), 1)

        self.handler.clear_session(sid)
        # In-memory buffer is cleared
        self.assertEqual(self.handler._session_buffers.get(sid), None)


if __name__ == "__main__":
    unittest.main()
