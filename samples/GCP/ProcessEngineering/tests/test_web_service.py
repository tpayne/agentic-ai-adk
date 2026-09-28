import importlib
import os
import sys
import unittest


class WebServiceSessionDeleteTest(unittest.TestCase):
    """Covers the DELETE /chat/<session_id> endpoint.

    Regression test for a review finding: the endpoint used to only pop the
    web_session_id -> (user_id, session_id) mapping from _web_sessions,
    leaving the actual ADK session (and its event history) alive in
    _web_session_service until process restart.
    """

    @classmethod
    def setUpClass(cls):
        # process_agents.common.agent validates model-provider credentials at
        # import time (configure_model_provider). This test never issues a
        # real LLM call -- session create/delete is pure in-memory bookkeeping
        # -- so a placeholder key is enough to satisfy that check.
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")

        # Other test modules in this suite (e.g. test_grounding_agent.py,
        # test_utils_agent_and_design_helpers.py) install lightweight stub
        # modules for google.adk/google.genai/pydantic/etc via
        # sys.modules.setdefault so they can unit-test agent code offline.
        # Those stubs only define the handful of names each stub-based test
        # needs (no LoopAgent/SequentialAgent/etc.) and, once installed,
        # never get removed for the rest of the process. This test needs
        # the real packages, so drop any stub/real copy of them plus every
        # process_agents module first and force genuine re-imports.
        _STUBBED_PREFIXES = (
            "google", "pydantic", "certifi", "requests", "urllib3",
            "yaml", "matplotlib", "networkx",
        )
        for name in list(sys.modules):
            if name in _STUBBED_PREFIXES or name.split(".", 1)[0] in _STUBBED_PREFIXES:
                del sys.modules[name]
        for name in list(sys.modules):
            if name == "process_agents" or name.startswith("process_agents."):
                del sys.modules[name]

        cls.agent = importlib.import_module("process_agents.common.agent")

    def setUp(self):
        agent = self.agent
        # Each test gets an isolated session_service/runner/session map so
        # state from other tests (or import-time construction) can't bleed in.
        agent._web_session_service = agent.InMemorySessionService()
        agent._web_runner = None
        with agent._web_sessions_lock:
            agent._web_sessions.clear()
        self.web_app = agent.build_web_app()
        self.client = self.web_app.test_client()

    def test_delete_removes_underlying_adk_session(self):
        agent = self.agent

        # Create the session directly via _get_or_create_web_session rather
        # than POSTing /chat, since /chat drives a real LLM turn through
        # Runner -- out of scope for this test, which only cares about
        # session bookkeeping around delete.
        web_session_id, user_id, session_id = agent.asyncio.run(
            agent._get_or_create_web_session(None)
        )

        # Sanity check: the ADK session actually exists before deletion.
        pre_delete = agent.asyncio.run(
            agent._web_session_service.get_session(
                app_name=agent._WEB_APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
        )
        self.assertIsNotNone(pre_delete)

        delete_resp = self.client.delete(f"/chat/{web_session_id}")
        self.assertEqual(delete_resp.status_code, 200)
        body = delete_resp.get_json()
        self.assertTrue(body["cleared"])

        # The web_session_id -> (user_id, session_id) mapping is gone...
        with agent._web_sessions_lock:
            self.assertNotIn(web_session_id, agent._web_sessions)

        # ...and, critically, so is the underlying ADK session itself.
        post_delete = agent.asyncio.run(
            agent._web_session_service.get_session(
                app_name=agent._WEB_APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
        )
        self.assertIsNone(post_delete)

    def test_delete_unknown_session_id_is_a_noop(self):
        delete_resp = self.client.delete("/chat/does-not-exist")
        self.assertEqual(delete_resp.status_code, 200)
        self.assertFalse(delete_resp.get_json()["cleared"])


if __name__ == "__main__":
    unittest.main()
