import asyncio
import importlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
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


class WebServiceSessionEvictionTest(unittest.TestCase):
    """_get_or_create_web_session's opportunistic idle-eviction sweep --
    regression coverage for a review finding: last_accessed is stamped
    once, at turn START (see _run_chat_turn/_mark_web_session_active), so a
    turn genuinely running longer than the idle timeout must not be
    evicted out from under itself just because its timestamp looks stale.
    _active_web_sessions is the signal the sweep actually checks to avoid
    exactly that race.
    """

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
        agent._web_session_service = agent.InMemorySessionService()
        agent._web_runner = None
        with agent._web_sessions_lock:
            agent._web_sessions.clear()
            agent._active_web_sessions.clear()
        agent._web_sessions_last_swept = 0.0

    def _make_entry(self, user_id, session_id, last_accessed):
        agent = self.agent
        agent.asyncio.run(
            agent._web_session_service.create_session(
                app_name=agent._WEB_APP_NAME, user_id=user_id, session_id=session_id, state={},
            )
        )
        return {"user_id": user_id, "session_id": session_id, "last_accessed": last_accessed}

    def test_idle_and_inactive_session_is_evicted(self):
        agent = self.agent
        stale = time.monotonic() - agent._WEB_SESSION_IDLE_TIMEOUT_SECONDS - 10
        with agent._web_sessions_lock:
            agent._web_sessions["idle"] = self._make_entry("u1", "s1", stale)
            agent._web_sessions["current"] = self._make_entry("u2", "s2", time.monotonic())

        result = agent.asyncio.run(agent._get_or_create_web_session("current"))

        self.assertEqual(result[0], "current")
        with agent._web_sessions_lock:
            self.assertNotIn("idle", agent._web_sessions)
        post_delete = agent.asyncio.run(
            agent._web_session_service.get_session(app_name=agent._WEB_APP_NAME, user_id="u1", session_id="s1")
        )
        self.assertIsNone(post_delete)

    def test_idle_but_active_turn_is_not_evicted(self):
        agent = self.agent
        stale = time.monotonic() - agent._WEB_SESSION_IDLE_TIMEOUT_SECONDS - 10
        with agent._web_sessions_lock:
            agent._web_sessions["mid-turn"] = self._make_entry("u1", "s1", stale)
            agent._web_sessions["current"] = self._make_entry("u2", "s2", time.monotonic())
            agent._active_web_sessions["mid-turn"] = 1

        agent.asyncio.run(agent._get_or_create_web_session("current"))

        with agent._web_sessions_lock:
            self.assertIn("mid-turn", agent._web_sessions)
        still_there = agent.asyncio.run(
            agent._web_session_service.get_session(app_name=agent._WEB_APP_NAME, user_id="u1", session_id="s1")
        )
        self.assertIsNotNone(still_there)

    def test_recently_accessed_session_is_never_swept(self):
        agent = self.agent
        with agent._web_sessions_lock:
            agent._web_sessions["current"] = self._make_entry("u1", "s1", time.monotonic())

        agent.asyncio.run(agent._get_or_create_web_session("current"))

        with agent._web_sessions_lock:
            self.assertIn("current", agent._web_sessions)

    def test_overlapping_turns_on_the_same_session_both_must_finish_before_eviction_is_possible(self):
        # Regression test for a review finding: _active_web_sessions used
        # to be a plain set -- two overlapping turns on the SAME session
        # both called _mark_web_session_active (idempotent add), but the
        # first to finish called _mark_web_session_inactive, which blindly
        # discarded the session from the set even though the SECOND turn
        # was still running. A sweep landing in that window could then
        # evict a session with a turn still genuinely in flight. The count
        # must only reach zero once BOTH turns have finished.
        agent = self.agent
        stale = time.monotonic() - agent._WEB_SESSION_IDLE_TIMEOUT_SECONDS - 10
        with agent._web_sessions_lock:
            agent._web_sessions["shared"] = self._make_entry("u1", "s1", stale)
            # A second, already-known, non-stale session to look up below --
            # avoids this test's sweep-triggering lookup also taking the
            # (heavier) "create a brand new session" path.
            agent._web_sessions["anchor"] = self._make_entry("u2", "s2", time.monotonic())

        agent._mark_web_session_active("shared")
        agent._mark_web_session_active("shared")  # a second, overlapping turn
        with agent._web_sessions_lock:
            self.assertEqual(agent._active_web_sessions["shared"], 2)

        agent._mark_web_session_inactive("shared")  # first turn finishes
        with agent._web_sessions_lock:
            self.assertIn("shared", agent._active_web_sessions)  # still pinned -- second turn active

        agent.asyncio.run(agent._get_or_create_web_session("anchor"))
        with agent._web_sessions_lock:
            self.assertIn("shared", agent._web_sessions)  # must survive the sweep above

        agent._mark_web_session_inactive("shared")  # second turn finishes
        with agent._web_sessions_lock:
            self.assertNotIn("shared", agent._active_web_sessions)

    def test_mark_inactive_refreshes_last_accessed_so_a_turn_ending_near_the_timeout_is_not_evicted(self):
        # Regression test: last_accessed was only ever stamped at turn
        # START. A turn that runs right up to (or past)
        # _WEB_SESSION_IDLE_TIMEOUT_SECONDS finished successfully, but
        # still carried its original, now-stale start timestamp the
        # instant it ended -- making the very next sweep see it as idle
        # and evict a session that had just finished normally.
        agent = self.agent
        turn_start = time.monotonic() - agent._WEB_SESSION_IDLE_TIMEOUT_SECONDS - 10
        with agent._web_sessions_lock:
            agent._web_sessions["just-finished"] = self._make_entry("u1", "s1", turn_start)
            agent._active_web_sessions["just-finished"] = 1

        agent._mark_web_session_inactive("just-finished")

        with agent._web_sessions_lock:
            self.assertGreater(agent._web_sessions["just-finished"]["last_accessed"], turn_start)


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
        stub_usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "model": "stub-model"}
        run_chat_turn = AsyncMock(return_value=("session-123", "stub response", stub_usage))
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
                            "usage": stub_usage,
                        },
                    )

        self.assertEqual(
            run_chat_turn.await_args_list,
            [call(None, "hello", files=[]), call(None, "hello", files=[])],
        )

    def test_status_is_open_and_does_not_consume_the_rate_limit(self):
        self.properties["webRateLimitPerMinute"] = 1
        self.client = self.agent.build_web_app(https=False).test_client()

        for _ in range(3):
            response = self.client.get("/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"status": "live", "model": self.agent.MODEL})

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

        async def fake_stream_chat_turn(user_id, session_id, query, event_queue, files=None):
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

        async def failing_stream_chat_turn(user_id, session_id, query, event_queue, files=None):
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

    def test_stream_recovers_with_an_error_event_if_the_turn_never_starts_at_all(self):
        # Regression test: unlike the test above (a failure INSIDE
        # _stream_chat_turn's own body, after its coroutine has already
        # started -- its own try/finally reliably pushes event_queue's
        # terminating None in that case), this simulates a failure DURING
        # CONSTRUCTION of that coroutine itself -- e.g. a bad argument
        # binding. _stream_chat_turn's own error handling never gets a
        # chance to run at all here, since the coroutine object was never
        # successfully created for loop.create_task to even schedule.
        # Confirmed directly: this previously left event_queue with no
        # sentinel whatsoever, hanging the whole SSE connection forever
        # (generate()'s consumer loop blocks on event_queue.get() with
        # nothing left to ever wake it). A plain (non-async) stand-in
        # reproduces this exactly -- calling it raises immediately,
        # before any coroutine/task exists.
        get_session = AsyncMock(
            return_value=("web-session-construct-fail", "user-1", "adk-session-1")
        )

        def broken_stream_chat_turn(user_id, session_id, query, event_queue, files=None):
            raise TypeError("simulated failure constructing the coroutine")

        with patch.object(self.agent, "_get_or_create_web_session", get_session), patch.object(
            self.agent, "_stream_chat_turn", broken_stream_chat_turn
        ):
            response = self.client.post(
                "/chat/stream", json={"query": "hello"}, headers=self._authorized_headers()
            )

        # Must complete at all (not hang) and surface the failure in-band,
        # same contract as the mid-turn-failure case above.
        self.assertEqual(response.status_code, 200)
        events = self._parse_sse(response.get_data(as_text=True))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "error")


class WebServiceChatStopTest(unittest.TestCase):
    """POST /chat/<session_id>/stop -- cancels an in-flight /chat/stream
    turn's REAL asyncio Task (see _active_stream_tasks in agent.py), not
    merely something the client can walk away from. Exercises actual
    concurrency (a real background thread running the streamed turn,
    stopped by a genuinely concurrent request) rather than mocking the
    cancellation mechanics away, since that race is the entire point of
    this feature."""

    API_KEY = "test-web-api-key"

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
        cls.agent = importlib.import_module("process_agents.common.agent")

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
        with self.agent._active_stream_tasks_lock:
            self.agent._active_stream_tasks.clear()
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

    def test_stop_when_nothing_is_in_flight_is_a_no_op(self):
        response = self.client.post(
            "/chat/some-unknown-session/stop", headers=self._authorized_headers()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"status": "ok", "session_id": "some-unknown-session", "stopped": False},
        )

    def test_stop_cancels_a_real_in_flight_turn(self):
        get_session = AsyncMock(
            return_value=("web-session-stop", "user-1", "adk-session-1")
        )
        started = threading.Event()
        cancelled = threading.Event()

        async def fake_stream_chat_turn(user_id, session_id, query, event_queue, files=None):
            event_queue.put({"status": "progress", "origin": "root_agent", "text": "starting"})
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                event_queue.put({"status": "stopped", "response": "partial"})
                raise
            finally:
                event_queue.put(None)

        with patch.object(self.agent, "_get_or_create_web_session", get_session), patch.object(
            self.agent, "_stream_chat_turn", fake_stream_chat_turn
        ):
            result = {}

            def run_stream():
                response = self.client.post(
                    "/chat/stream", json={"query": "hello"}, headers=self._authorized_headers()
                )
                result["events"] = self._parse_sse(response.get_data(as_text=True))

            stream_thread = threading.Thread(target=run_stream)
            stream_thread.start()

            self.assertTrue(started.wait(timeout=5), "the turn never started")
            # The background thread registers itself in _active_stream_tasks
            # right before it starts running -- give it a moment to land.
            for _ in range(50):
                with self.agent._active_stream_tasks_lock:
                    if "web-session-stop" in self.agent._active_stream_tasks:
                        break
                time.sleep(0.05)

            stop_response = self.client.post(
                "/chat/web-session-stop/stop", headers=self._authorized_headers()
            )
            self.assertEqual(stop_response.status_code, 200)
            self.assertEqual(
                stop_response.get_json(),
                {"status": "ok", "session_id": "web-session-stop", "stopped": True},
            )

            stream_thread.join(timeout=5)

        self.assertTrue(cancelled.is_set(), "the Task was never actually cancelled")
        self.assertEqual(
            [e["status"] for e in result["events"]], ["progress", "stopped"]
        )
        self.assertEqual(result["events"][-1]["response"], "partial")
        # Cleaned up on its own -- no leftover entry for a turn that's over.
        with self.agent._active_stream_tasks_lock:
            self.assertNotIn("web-session-stop", self.agent._active_stream_tasks)

    def test_stop_requires_a_configured_api_key(self):
        response = self.client.post("/chat/some-session/stop")
        self.assertEqual(response.status_code, 401)


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


class UsageAccumulationTest(unittest.TestCase):
    """_accumulate_event_usage -- the Token Usage tab's per-turn token
    accounting. Callers (_run_chat_turn/_stream_chat_turn) only invoke this
    for NON-PARTIAL events -- ADK's own Runner only ever persists
    non-partial events into session history (see Runner._should_append_event
    in the installed google-adk package), so there is exactly one
    non-partial event per real model call and no risk of counting one
    streamed call's usage more than once; this function itself does no
    dedup of its own, it just adds whatever usage_metadata is present."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
        cls.agent = importlib.import_module("process_agents.common.agent")

    @staticmethod
    def _event(prompt, candidates, total):
        usage = None
        if prompt is not None:
            usage = SimpleNamespace(
                prompt_token_count=prompt,
                candidates_token_count=candidates,
                total_token_count=total,
            )
        return SimpleNamespace(usage_metadata=usage)

    def test_events_with_no_usage_metadata_are_skipped(self):
        totals = self.agent._new_usage_totals()
        self.agent._accumulate_event_usage(self._event(None, None, None), totals)
        self.assertEqual(totals, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    def test_adds_one_events_usage_into_totals(self):
        totals = self.agent._new_usage_totals()
        self.agent._accumulate_event_usage(self._event(10, 5, 15), totals)
        self.assertEqual(
            totals, {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        )

    def test_a_second_distinct_call_adds_to_the_running_total(self):
        totals = self.agent._new_usage_totals()
        # Two separate non-partial events -- e.g. one per sub-agent/tool-
        # using step in a multi-agent turn -- each contribute their own
        # usage; the running total is their sum.
        self.agent._accumulate_event_usage(self._event(10, 5, 15), totals)
        self.agent._accumulate_event_usage(self._event(20, 8, 28), totals)
        self.assertEqual(
            totals, {"prompt_tokens": 30, "completion_tokens": 13, "total_tokens": 43}
        )

    def test_events_without_usage_interleaved_are_simply_skipped(self):
        totals = self.agent._new_usage_totals()
        self.agent._accumulate_event_usage(self._event(10, 5, 15), totals)
        self.agent._accumulate_event_usage(self._event(None, None, None), totals)
        self.agent._accumulate_event_usage(self._event(10, 5, 15), totals)
        # Two REAL (non-partial, by the caller's own contract) events with
        # usage, plus one with none -- both real ones count.
        self.assertEqual(
            totals, {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
        )


class ParseAttachmentsTest(unittest.TestCase):
    """_parse_attachments -- validates/decodes POST /chat or /chat/stream's
    optional "files" field server-side, re-checking size/count even though
    the web client enforces the same limits before ever sending (a client
    is never a trusted boundary). Deliberately kept identical (same
    checks, same error wording) to the Neurosan port's own
    cli.py._parse_attachments -- see that file's own TestParseAttachments
    for the mirrored coverage."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
        cls.agent = importlib.import_module("process_agents.common.agent")

    @staticmethod
    def _b64(raw: bytes) -> str:
        import base64
        return base64.b64encode(raw).decode("ascii")

    def test_absent_files_is_not_an_error(self):
        files, error = self.agent._parse_attachments({})
        self.assertEqual(files, [])
        self.assertIsNone(error)

    def test_decodes_a_valid_file(self):
        payload = {"files": [{"name": "notes.txt", "mime_type": "text/plain", "data_base64": self._b64(b"hello")}]}
        files, error = self.agent._parse_attachments(payload)
        self.assertIsNone(error)
        self.assertEqual(files, [{"name": "notes.txt", "mime_type": "text/plain", "data": b"hello"}])

    def test_files_not_a_list_is_rejected(self):
        files, error = self.agent._parse_attachments({"files": "not-a-list"})
        self.assertIsNone(files)
        self.assertIn("must be a list", error)

    def test_too_many_files_is_rejected(self):
        entry = {"name": "x.txt", "mime_type": "text/plain", "data_base64": self._b64(b"x")}
        payload = {"files": [entry] * (self.agent.ATTACHMENT_MAX_FILES + 1)}
        files, error = self.agent._parse_attachments(payload)
        self.assertIsNone(files)
        self.assertIn("Too many", error)

    def test_entry_missing_mime_type_is_rejected(self):
        payload = {"files": [{"name": "x.txt", "data_base64": self._b64(b"x")}]}
        files, error = self.agent._parse_attachments(payload)
        self.assertIsNone(files)
        self.assertIn("mime_type", error)

    def test_invalid_base64_is_rejected(self):
        payload = {"files": [{"name": "x.txt", "mime_type": "text/plain", "data_base64": "not valid base64!!"}]}
        files, error = self.agent._parse_attachments(payload)
        self.assertIsNone(files)
        self.assertIn("invalid base64", error)

    def test_oversized_file_is_rejected(self):
        oversized = self._b64(b"x" * (self.agent.ATTACHMENT_MAX_BYTES + 1))
        payload = {"files": [{"name": "big.bin", "mime_type": "application/octet-stream", "data_base64": oversized}]}
        files, error = self.agent._parse_attachments(payload)
        self.assertIsNone(files)
        self.assertIn("exceeds", error)

    def test_file_at_exactly_the_limit_is_accepted(self):
        at_limit = self._b64(b"x" * self.agent.ATTACHMENT_MAX_BYTES)
        payload = {"files": [{"name": "ok.bin", "mime_type": "application/octet-stream", "data_base64": at_limit}]}
        files, error = self.agent._parse_attachments(payload)
        self.assertIsNone(error)
        self.assertEqual(len(files[0]["data"]), self.agent.ATTACHMENT_MAX_BYTES)

    def test_same_limits_as_the_neurosan_port(self):
        # Not a hard architectural requirement, but confirmed deliberate
        # (see both files' own ATTACHMENT_MAX_FILES/ATTACHMENT_MAX_BYTES
        # comments) -- the shared WebClient's behavior shouldn't change
        # depending on which backend it's talking to.
        self.assertEqual(self.agent.ATTACHMENT_MAX_FILES, 4)
        self.assertEqual(self.agent.ATTACHMENT_MAX_BYTES, 8 * 1024 * 1024)


class ContentPartsForTurnTest(unittest.TestCase):
    """_content_parts_for_turn -- builds the Content.parts list Gemini
    actually receives. Unlike the Neurosan port (text-extraction
    workaround, see that project's own cli.py), attached files reach
    Gemini as genuine multimodal content here -- a real types.Part.
    from_bytes per file, not just a text summary."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
        cls.agent = importlib.import_module("process_agents.common.agent")

    def test_no_files_produces_just_the_text_part(self):
        parts = self.agent._content_parts_for_turn("hello", None)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].text, "hello")

    def test_empty_files_list_produces_just_the_text_part(self):
        parts = self.agent._content_parts_for_turn("hello", [])
        self.assertEqual(len(parts), 1)

    def test_one_file_adds_one_real_multimodal_part(self):
        files = [{"name": "diagram.png", "mime_type": "image/png", "data": b"\x89PNGnotreal"}]
        parts = self.agent._content_parts_for_turn("describe this", files)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].text, "describe this")
        # A genuine multimodal Part carries inline_data (bytes + mime
        # type), not a text summary of the file.
        self.assertIsNotNone(parts[1].inline_data)
        self.assertEqual(parts[1].inline_data.mime_type, "image/png")
        self.assertEqual(parts[1].inline_data.data, b"\x89PNGnotreal")

    def test_multiple_files_each_get_their_own_part_in_order(self):
        files = [
            {"name": "a.png", "mime_type": "image/png", "data": b"AAA"},
            {"name": "b.pdf", "mime_type": "application/pdf", "data": b"BBB"},
        ]
        parts = self.agent._content_parts_for_turn("compare these", files)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[1].inline_data.data, b"AAA")
        self.assertEqual(parts[2].inline_data.data, b"BBB")

    def test_used_directly_as_a_contents_parts_list(self):
        files = [{"name": "a.txt", "mime_type": "text/plain", "data": b"hi"}]
        content = self.agent.types.Content(role="user", parts=self.agent._content_parts_for_turn("q", files))
        self.assertEqual(content.role, "user")
        self.assertEqual(len(content.parts), 2)


if __name__ == "__main__":
    unittest.main()
