import importlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock, call, patch


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


class WebServiceInitRaceTest(unittest.TestCase):
    """Regression test for a review finding: two concurrent first requests
    could each see _web_runner/_web_session_service as None and build their
    own, leaving the shared runner bound to whichever one lost the race --
    sessions created by the other thread then live in a session_service the
    runner never queries. _web_runtime_init_lock in agent.py fixes this by
    making the check-then-init block a single critical section."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
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
        agent._web_session_service = None
        agent._web_runner = None
        with agent._web_sessions_lock:
            agent._web_sessions.clear()

    def test_concurrent_first_requests_initialize_the_runtime_exactly_once(self):
        agent = self.agent
        init_count = {"n": 0}
        init_count_lock = threading.Lock()
        real_service_cls = agent.InMemorySessionService

        class SlowInMemorySessionService(real_service_cls):
            def __init__(self, *args, **kwargs):
                # Widen the race window so two threads both reliably observe
                # _web_session_service/_web_runner as None before either
                # finishes initializing it, the way two real concurrent
                # first HTTP requests could.
                time.sleep(0.05)
                with init_count_lock:
                    init_count["n"] += 1
                super().__init__(*args, **kwargs)

        results = []
        errors = []

        def worker():
            try:
                results.append(agent.asyncio.run(agent._get_or_create_web_session(None)))
            except Exception as exc:  # pragma: no cover - surfaced via errors list
                errors.append(exc)

        with patch.object(agent, "InMemorySessionService", SlowInMemorySessionService):
            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        self.assertEqual(init_count["n"], 1, "session service was initialized more than once")

        # Every thread's session must be reachable through the one shared
        # runner/session_service that ended up installed -- not stranded in
        # a separate service instance a different thread built and lost.
        for _web_session_id, user_id, session_id in results:
            session = agent.asyncio.run(
                agent._web_session_service.get_session(
                    app_name=agent._WEB_APP_NAME,
                    user_id=user_id,
                    session_id=session_id,
                )
            )
            self.assertIsNotNone(session)


class WebServiceInsecureDefaultTest(unittest.TestCase):
    """Regression test for a review finding: run_web_service would happily
    bind 0.0.0.0 with no webApiKey configured, exposing an unauthenticated,
    model-backed chat API to any reachable client. It must now refuse to
    start unless host is loopback, webApiKey is set, or the operator
    explicitly opts in via allowInsecureWebService."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
        cls.agent = importlib.import_module("process_agents.common.agent")

    def _run_with_properties(self, properties: dict):
        agent = self.agent

        def fake_get_property(name, section="SETTINGS", default=None):
            return properties.get(name, default)

        with patch.object(agent, "getProperty", side_effect=fake_get_property), \
             patch.object(agent, "build_web_app") as mock_build_web_app, \
             patch.object(agent, "display_text"):
            agent.run_web_service(port=8080, use_https=False)
            return mock_build_web_app

    def test_refuses_to_start_on_non_loopback_host_with_no_api_key(self):
        with self.assertRaises(SystemExit):
            self._run_with_properties({"host": "0.0.0.0"})

    def test_starts_on_loopback_host_with_no_api_key(self):
        mock_build_web_app = self._run_with_properties({"host": "127.0.0.1"})
        mock_build_web_app.assert_called_once()

    def test_starts_on_non_loopback_host_with_api_key_configured(self):
        mock_build_web_app = self._run_with_properties(
            {"host": "0.0.0.0", "webApiKey": "a-long-random-value"}
        )
        mock_build_web_app.assert_called_once()

    def test_starts_on_non_loopback_host_with_explicit_opt_in(self):
        mock_build_web_app = self._run_with_properties(
            {"host": "0.0.0.0", "allowInsecureWebService": True}
        )
        mock_build_web_app.assert_called_once()


class WebServiceRequestControlsTest(unittest.TestCase):
    """Exercise the Flask request boundary without running an ADK/model turn."""

    API_KEY = "test-web-api-key"

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
        cls.agent = importlib.import_module("process_agents.common.agent")

    def setUp(self):
        self.properties = {
            "webApiKey": self.API_KEY,
            "webRateLimitPerMinute": 100,
        }
        self.property_patch = patch.object(
            self.agent,
            "getProperty",
            side_effect=lambda name, section="SETTINGS", default=None: self.properties.get(
                name, default
            ),
        )
        self.property_patch.start()
        self.addCleanup(self.property_patch.stop)
        self.display_patch = patch.object(self.agent, "display_text")
        self.display_patch.start()
        self.addCleanup(self.display_patch.stop)

        with self.agent._web_rate_limit_lock:
            self.agent._web_rate_limit_state.clear()
        self.client = self.agent.build_web_app(https=False).test_client()

    def _authorized_headers(self):
        return {"X-API-Key": self.API_KEY}

    def test_chat_requires_a_configured_api_key(self):
        missing = self.client.post("/chat", json={"query": "hello"})
        invalid = self.client.post(
            "/chat", json={"query": "hello"}, headers={"X-API-Key": "wrong"}
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.get_json()["error"], "Unauthorized")
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.get_json()["error"], "Unauthorized")

    def test_valid_api_key_in_supported_headers_reaches_chat_handler(self):
        run_chat_turn = AsyncMock(return_value=("session-123", "stub response"))
        bearer_scheme = "Bearer"
        with patch.object(self.agent, "_run_chat_turn", run_chat_turn):
            for headers in (
                self._authorized_headers(),
                {"Authorization": bearer_scheme + " " + self.API_KEY},
            ):
                with self.subTest(headers=headers):
                    response = self.client.post(
                        "/chat",
                        json={"query": "hello"},
                        headers=headers,
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.get_json(),
                        {
                            "status": "ok",
                            "session_id": "session-123",
                            "query": "hello",
                            "response": "stub response",
                        },
                    )

        self.assertEqual(
            run_chat_turn.await_args_list,
            [call(None, "hello"), call(None, "hello")],
        )

    def test_status_is_open_and_does_not_consume_the_rate_limit(self):
        self.properties["webRateLimitPerMinute"] = 1
        self.client = self.agent.build_web_app(https=False).test_client()

        for _ in range(3):
            response = self.client.get("/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"status": "live"})

        first_protected_request = self.client.delete(
            "/chat/unknown-session", headers=self._authorized_headers()
        )
        second_protected_request = self.client.delete(
            "/chat/another-unknown-session", headers=self._authorized_headers()
        )
        self.assertEqual(first_protected_request.status_code, 200)
        self.assertEqual(second_protected_request.status_code, 429)
        self.assertEqual(
            second_protected_request.get_json()["error"], "Rate limit exceeded"
        )

    def test_invalid_json_and_query_values_are_rejected_before_chat_runs(self):
        invalid_requests = [
            {"data": "{not-json", "content_type": "application/json"},
            {"json": {}},
            {"json": {"query": ""}},
            {"json": {"query": "  "}},
            {"json": {"query": 12}},
            {"json": {"query": ["not", "a", "string"]}},
        ]
        run_chat_turn = AsyncMock()

        with patch.object(self.agent, "_run_chat_turn", run_chat_turn):
            for request_data in invalid_requests:
                with self.subTest(request_data=request_data):
                    response = self.client.post(
                        "/chat",
                        headers=self._authorized_headers(),
                        **request_data,
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.get_json()["status"], "error")
                    self.assertIn("query", response.get_json()["error"])

        run_chat_turn.assert_not_awaited()


class WebServiceChatStreamTest(unittest.TestCase):
    """Covers the POST /chat/stream endpoint (streaming counterpart to
    POST /chat) without running a live ADK/model turn or a real
    _web_runner.run_async -- _stream_chat_turn itself is stubbed out, same
    as _run_chat_turn is for WebServiceRequestControlsTest's /chat tests,
    since the thread+queue bridge in chat_stream's own generate() is what
    these tests actually exercise."""

    API_KEY = "test-web-api-key"

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
        cls.agent = importlib.import_module("process_agents.common.agent")

    def setUp(self):
        self.properties = {
            "webApiKey": self.API_KEY,
            "webRateLimitPerMinute": 100,
        }
        self.property_patch = patch.object(
            self.agent,
            "getProperty",
            side_effect=lambda name, section="SETTINGS", default=None: self.properties.get(
                name, default
            ),
        )
        self.property_patch.start()
        self.addCleanup(self.property_patch.stop)
        self.display_patch = patch.object(self.agent, "display_text")
        self.display_patch.start()
        self.addCleanup(self.display_patch.stop)

        with self.agent._web_rate_limit_lock:
            self.agent._web_rate_limit_state.clear()
        self.client = self.agent.build_web_app(https=False).test_client()

    def _authorized_headers(self):
        return {"X-API-Key": self.API_KEY}

    @staticmethod
    def _parse_sse(body):
        return [
            json.loads(line[len("data: "):])
            for line in body.strip().split("\n\n")
            if line.startswith("data: ")
        ]

    def test_stream_requires_a_configured_api_key(self):
        response = self.client.post("/chat/stream", json={"query": "hello"})
        self.assertEqual(response.status_code, 401)

    def test_stream_requires_a_nonempty_query(self):
        response = self.client.post(
            "/chat/stream", json={}, headers=self._authorized_headers()
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], "error")

    def test_stream_emits_sse_events_ending_in_done_and_sets_the_cookie(self):
        get_session = AsyncMock(
            return_value=("web-session-123", "user-1", "adk-session-1")
        )

        async def fake_stream_chat_turn(user_id, session_id, query, event_queue):
            self.assertEqual(user_id, "user-1")
            self.assertEqual(session_id, "adk-session-1")
            self.assertEqual(query, "hello")
            event_queue.put({"status": "progress", "origin": "root_agent", "text": "Calling foo"})
            event_queue.put({"status": "delta", "text": "partial"})
            event_queue.put({"status": "delta", "text": "final text"})
            event_queue.put({"status": "done", "response": "final text"})
            event_queue.put(None)

        with patch.object(self.agent, "_get_or_create_web_session", get_session), patch.object(
            self.agent, "_stream_chat_turn", fake_stream_chat_turn
        ):
            response = self.client.post(
                "/chat/stream", json={"query": "hello"}, headers=self._authorized_headers()
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith("text/event-stream"))
        self.assertIn(self.agent.WEB_SESSION_COOKIE, response.headers.get("Set-Cookie", ""))

        events = self._parse_sse(response.get_data(as_text=True))
        self.assertEqual([e["status"] for e in events], ["progress", "delta", "delta", "done"])
        self.assertEqual(events[-1]["response"], "final text")
        self.assertTrue(all(e["session_id"] == "web-session-123" for e in events))

    def test_stream_surfaces_an_in_band_error_event_without_a_500(self):
        get_session = AsyncMock(
            return_value=("web-session-err", "user-1", "adk-session-1")
        )

        async def failing_stream_chat_turn(user_id, session_id, query, event_queue):
            event_queue.put({"status": "progress", "origin": "root_agent", "text": "starting"})
            event_queue.put({"status": "error", "error": "An internal error has occurred."})
            event_queue.put(None)

        with patch.object(self.agent, "_get_or_create_web_session", get_session), patch.object(
            self.agent, "_stream_chat_turn", failing_stream_chat_turn
        ):
            response = self.client.post(
                "/chat/stream", json={"query": "hello"}, headers=self._authorized_headers()
            )

        # Headers (and the 200) are already sent by the time an error can
        # happen mid-turn -- it must arrive as an in-band SSE event, not
        # an HTTP 500.
        self.assertEqual(response.status_code, 200)
        events = self._parse_sse(response.get_data(as_text=True))
        self.assertEqual(events[0]["status"], "progress")
        self.assertEqual(events[-1]["status"], "error")


class WebServiceArtifactRouteTest(unittest.TestCase):
    """GET /artifacts/<name> -- read-only access to output/process_data.json
    /output/design_data.json for the web client's "Process / Design" tab.
    utils_agent.PROJECT_ROOT is patched to an isolated tmp dir for every
    test here so these don't depend on (or disturb) this checkout's own
    real output/ directory, whose contents vary run to run."""

    API_KEY = "test-web-api-key"

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
        cls.agent = importlib.import_module("process_agents.common.agent")
        cls.utils_agent = importlib.import_module("process_agents.common.utils_agent")

    def setUp(self):
        self.properties = {"webApiKey": self.API_KEY, "webRateLimitPerMinute": 100}
        self.property_patch = patch.object(
            self.agent,
            "getProperty",
            side_effect=lambda name, section="SETTINGS", default=None: self.properties.get(
                name, default
            ),
        )
        self.property_patch.start()
        self.addCleanup(self.property_patch.stop)
        self.display_patch = patch.object(self.agent, "display_text")
        self.display_patch.start()
        self.addCleanup(self.display_patch.stop)

        with self.agent._web_rate_limit_lock:
            self.agent._web_rate_limit_state.clear()

        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.output_dir = os.path.join(self.tmp_dir.name, "output")
        os.makedirs(self.output_dir)
        self.project_root_patch = patch.object(self.utils_agent, "PROJECT_ROOT", self.tmp_dir.name)
        self.project_root_patch.start()
        self.addCleanup(self.project_root_patch.stop)

        self.client = self.agent.build_web_app(https=False).test_client()

    def _authorized_headers(self):
        return {"X-API-Key": self.API_KEY}

    def _write(self, filename, content):
        with open(os.path.join(self.output_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)

    def test_returns_parsed_json_when_the_file_exists(self):
        self._write("process_data.json", '{"foo": "bar"}')
        response = self.client.get("/artifacts/process", headers=self._authorized_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(), {"status": "ok", "name": "process", "data": {"foo": "bar"}}
        )

    def test_design_artifact_name_maps_to_design_data_json(self):
        self._write("design_data.json", '{"doc": true}')
        response = self.client.get("/artifacts/design", headers=self._authorized_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"], {"doc": True})

    def test_404_when_the_file_has_not_been_generated_yet(self):
        response = self.client.get("/artifacts/process", headers=self._authorized_headers())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["status"], "error")

    def test_400_for_an_unrecognized_artifact_name(self):
        response = self.client.get("/artifacts/bogus", headers=self._authorized_headers())
        self.assertEqual(response.status_code, 400)

    def test_500_for_unparseable_json_on_disk(self):
        self._write("process_data.json", "{not valid json")
        response = self.client.get("/artifacts/process", headers=self._authorized_headers())
        self.assertEqual(response.status_code, 500)

    def test_requires_a_configured_api_key(self):
        self._write("process_data.json", "{}")
        response = self.client.get("/artifacts/process")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
