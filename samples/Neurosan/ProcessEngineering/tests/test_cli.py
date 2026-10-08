"""Unit tests for cli.py's own control-flow logic (argument parsing, control
lines, shell-escape detection) -- the parts that don't require a live LLM
credential to exercise. ChatSession itself (the part that actually talks to
neuro-san) is exercised manually/at the integration level elsewhere in this
project (ns chat), the same way every other network's LLM-backed behavior
is -- there's no API key in this environment to drive a real turn through
it in a unit test.
"""

import asyncio
from types import SimpleNamespace

import pytest

import cli


def test_is_shell_command():
    assert cli.is_shell_command("$ echo hi")
    assert cli.is_shell_command("  $ echo hi")
    assert not cli.is_shell_command("echo hi")
    assert not cli.is_shell_command(None)
    assert not cli.is_shell_command("")


def test_parser_rejects_http_or_port_without_detached():
    parser = cli.build_parser()
    args = parser.parse_args(["--http"])
    assert args.detached is False and args.http is True
    # The actual rejection happens in run_cli(), not argparse itself (it's
    # a cross-flag rule, not expressible via mutually_exclusive_group) --
    # confirm the condition run_cli() checks would trip here.
    assert not args.detached and (args.http or args.port is not None)


def test_parser_mode_flags_are_mutually_exclusive():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["-i", "hello", "-f", "some_file.txt"])


def test_parser_defaults_to_process_architect_agent():
    parser = cli.build_parser()
    args = parser.parse_args([])
    assert args.agent == "process_architect"
    assert args.file is None
    assert args.input is None
    assert args.detached is False


class _StubSession:
    """Stands in for cli.ChatSession in control-line tests -- records
    every line actually sent to .send() so a test can assert the agent
    was (or wasn't) invoked, without needing a live LLM credential."""

    def __init__(self):
        self.sent = []

    def send(self, text: str) -> str:
        self.sent.append(text)
        return f"echo: {text}"


def test_handle_logical_line_exit_quit_stop_signal_termination():
    holder = [_StubSession()]
    for word in ("exit", "quit", "stop", "EXIT"):
        should_stop = asyncio.run(cli.handle_logical_line(word, holder, "process_architect"))
        assert should_stop is True
    assert holder[0].sent == []  # control words are never sent to the agent


def test_handle_logical_line_comment_is_not_sent_to_agent():
    holder = [_StubSession()]
    should_stop = asyncio.run(cli.handle_logical_line("# just a note", holder, "process_architect"))
    assert should_stop is False
    assert holder[0].sent == []


def test_handle_logical_line_sleep_does_not_hit_the_agent(monkeypatch):
    sleeps = []
    real_sleep = asyncio.sleep

    async def fake_sleep(secs):
        sleeps.append(secs)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    holder = [_StubSession()]
    should_stop = asyncio.run(cli.handle_logical_line("sleep 0.01", holder, "process_architect"))
    assert should_stop is False
    assert sleeps == [0.01]
    assert holder[0].sent == []


def test_handle_logical_line_shell_escape_does_not_hit_the_agent(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_shell_command", lambda line: calls.append(line))
    holder = [_StubSession()]
    should_stop = asyncio.run(cli.handle_logical_line("$ echo hi", holder, "process_architect"))
    assert should_stop is False
    assert calls == ["$ echo hi"]
    assert holder[0].sent == []


def test_handle_logical_line_ordinary_text_is_sent_to_the_agent():
    holder = [_StubSession()]
    should_stop = asyncio.run(cli.handle_logical_line("design a vendor onboarding process", holder, "process_architect"))
    assert should_stop is False
    assert holder[0].sent == ["design a vendor onboarding process"]


def test_handle_logical_line_clear_replaces_the_session(monkeypatch):
    original = _StubSession()
    replacement = _StubSession()
    created = [replacement]
    monkeypatch.setattr(cli, "ChatSession", lambda agent_name: created.pop(0))
    holder = [original]
    should_stop = asyncio.run(cli.handle_logical_line("clear", holder, "process_architect"))
    assert should_stop is False
    assert holder[0] is replacement


def test_handle_logical_line_interactive_mode_does_not_echo_input(capsys):
    """Default echo_input=False (interactive mode) must not print the line
    back -- the terminal already echoed what was typed; doing it again is
    the exact duplicate-input bug this guards against."""
    holder = [_StubSession()]
    asyncio.run(cli.handle_logical_line("hello", holder, "process_architect"))
    captured = capsys.readouterr()
    assert "[user" not in captured.out


def test_handle_logical_line_file_mode_echoes_input(capsys):
    """echo_input=True (process_file's own call) must print the line back
    -- there's no terminal echo for lines read from a file."""
    holder = [_StubSession()]
    asyncio.run(cli.handle_logical_line("hello", holder, "process_architect", echo_input=True))
    captured = capsys.readouterr()
    assert "[user-file]: hello" in captured.out


class TestLiveTraceMessageProcessor:
    """cli.LiveTraceMessageProcessor logs through the standard `logging`
    module at DEBUG (cli._trace_logger), not a bespoke print mechanism --
    silent unless LOGLEVEL=DEBUG is set, same as every other logger in
    this project."""

    def test_skips_empty_progress_heartbeat(self, caplog):
        proc = cli.LiveTraceMessageProcessor()
        with caplog.at_level("DEBUG", logger="ProcessArchitect.CLI.Trace"):
            proc.process_message({"text": "", "origin": []}, cli.ChatMessageType.AGENT_PROGRESS)
        assert caplog.records == []

    def test_logs_agent_text_message_at_debug(self, caplog):
        proc = cli.LiveTraceMessageProcessor()
        with caplog.at_level("DEBUG", logger="ProcessArchitect.CLI.Trace"):
            proc.process_message(
                {"text": "Calling reset_loop_state now.", "origin": [{"tool": "cloudarch"}, {"tool": "CloudArch_Pipeline"}]},
                cli.ChatMessageType.AGENT,
            )
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "DEBUG"
        message = caplog.records[0].getMessage()
        assert "cloudarch.CloudArch_Pipeline" in message
        assert "Calling reset_loop_state now." in message

    def test_logs_structure_preview_and_tool_result_origin(self, caplog):
        proc = cli.LiveTraceMessageProcessor()
        with caplog.at_level("DEBUG", logger="ProcessArchitect.CLI.Trace"):
            proc.process_message(
                {
                    "structure": {"status": "OK"},
                    "origin": [{"tool": "cloudarch"}, {"tool": "reset_loop_state"}],
                    "tool_result_origin": [{"tool": "cloudarch"}, {"tool": "reset_loop_state"}],
                },
                cli.ChatMessageType.AGENT_TOOL_RESULT,
            )
        message = caplog.records[0].getMessage()
        assert "<structure: status>" in message
        assert "result from" in message

    def test_silent_when_debug_not_enabled(self, caplog):
        """Default level is WARNING (see the LOGLEVEL setup in cli.py) --
        with DEBUG not enabled, process_message must not even format a
        record, let alone emit one."""
        proc = cli.LiveTraceMessageProcessor()
        with caplog.at_level("WARNING", logger="ProcessArchitect.CLI.Trace"):
            proc.process_message({"text": "hello", "origin": []}, cli.ChatMessageType.AGENT)
        assert caplog.records == []


class TestExtractUsage:
    """_extract_usage -- maps neuro-san's own token_accounting shape onto
    the {prompt_tokens, completion_tokens, total_tokens, model} shape the
    web client's Token Usage tab expects (same keys the ADK original's own
    usage field uses)."""

    def test_none_or_empty_accounting_maps_to_none(self):
        assert cli._extract_usage(None) is None
        assert cli._extract_usage({}) is None

    def test_maps_scalar_fields_and_single_model_name(self):
        accounting = {
            "total_tokens": 150,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "models": {"GoogleGenAI": {"gemini-3-flash": {"total_tokens": 150}}},
        }
        assert cli._extract_usage(accounting) == {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "model": "gemini-3-flash",
        }

    def test_joins_multiple_distinct_model_names(self):
        accounting = {
            "total_tokens": 300,
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "models": {
                "GoogleGenAI": {"gemini-3-flash": {"total_tokens": 150}},
                "OpenAI": {"gpt-4o": {"total_tokens": 150}},
            },
        }
        assert cli._extract_usage(accounting)["model"] == "gemini-3-flash + gpt-4o"

    def test_missing_models_key_maps_to_none_model(self):
        accounting = {"total_tokens": 10, "prompt_tokens": 7, "completion_tokens": 3}
        usage = cli._extract_usage(accounting)
        assert usage["model"] is None
        assert usage["total_tokens"] == 10


def test_send_logs_token_accounting_at_info(caplog):
    """ChatSession.send must surface token_accounting (previously silently
    discarded) via the standard logger at INFO, not swallow it."""
    session = cli.ChatSession.__new__(cli.ChatSession)  # bypass __init__'s real session setup
    session.sly_data = None
    session.chat_context = None

    class _StubInputProcessor:
        def process_once(self, state):
            return {
                "last_chat_response": "done",
                "sly_data": {},
                "chat_context": {},
                "token_accounting": {
                    "total_tokens": 42,
                    "prompt_tokens": 30,
                    "completion_tokens": 12,
                    "models": {"GoogleGenAI": {"gemini-3-flash": {"total_tokens": 42}}},
                },
            }

    session.input_processor = _StubInputProcessor()
    with caplog.at_level("INFO", logger="ProcessArchitect.CLI.Trace"):
        result = session.send("hi")
    assert result == "done"
    assert any("total_tokens" in r.getMessage() for r in caplog.records)
    # The Token Usage tab's /chat route reads session.last_usage after
    # send() returns -- confirm send() actually populates it, not just logs.
    assert session.last_usage == {
        "prompt_tokens": 30,
        "completion_tokens": 12,
        "total_tokens": 42,
        "model": "gemini-3-flash",
    }


class _StubStreamingProcessor:
    """Stands in for StreamingInputProcessor.get_message_processor()'s
    return value -- a BasicMessageProcessor -- tracking just enough state
    (the latest "answer"-type message's text) for send_streaming's own
    compiled-answer-changed check to exercise realistically."""

    def __init__(self):
        self._answer = None
        self.messages = []

    def process_message(self, response):
        self.messages.append(response)
        if response.get("type") == "answer":
            self._answer = response.get("text")

    def get_compiled_answer(self):
        return self._answer

    def get_chat_context(self):
        return {"ctx": 1}

    def get_sly_data(self):
        return {"sly": 1}

    def get_token_accounting(self):
        return {}


class _StubStreamingInputProcessor:
    def __init__(self):
        self.processor = _StubStreamingProcessor()
        self.reset_called = False

    def get_message_processor(self):
        return self.processor

    def formulate_chat_request(self, text, sly_data, chat_context, chat_filter):
        return {"user_message": {"text": text}}

    def reset(self):
        self.reset_called = True


class _StubStreamingSession:
    """Stands in for neuro-san's DirectAgentSession -- streaming_chat()
    yields messages exactly like the real one, including a progress
    heartbeat (empty text, no structure) that send_streaming must skip,
    same as LiveTraceMessageProcessor already does for the debug trace."""

    def streaming_chat(self, chat_request):
        yield {"response": {"type": "progress", "origin": [{"tool": "cloudarch"}], "text": "Calling Reviewer..."}}
        yield {"response": {"type": "progress", "origin": [], "text": ""}}  # heartbeat -- must be skipped
        yield {"response": {"type": "answer", "origin": [{"tool": "cloudarch"}], "text": "Partial answer"}}
        yield {"response": {"type": "answer", "origin": [{"tool": "cloudarch"}], "text": "Final answer"}}


def _make_streaming_session():
    session = cli.ChatSession.__new__(cli.ChatSession)  # bypass __init__'s real session setup
    session.sly_data = None
    session.chat_context = None
    session.session = _StubStreamingSession()
    session.input_processor = _StubStreamingInputProcessor()
    return session


class TestChatSessionSendStreaming:
    """ChatSession.send_streaming -- the generator POST /chat/stream (see
    TestChatStreamRoute) is built on."""

    def test_yields_progress_then_deltas_then_done(self):
        session = _make_streaming_session()
        events = list(session.send_streaming("hello"))
        assert events == [
            {"status": "progress", "origin": "cloudarch", "text": "Calling Reviewer..."},
            {"status": "delta", "text": "Partial answer"},
            {"status": "delta", "text": "Final answer"},
            # _StubStreamingProcessor.get_token_accounting() returns {} --
            # "no accounting at all" -- so _extract_usage maps that to None
            # (see TestExtractUsage below for the real-shape mapping).
            {"status": "done", "response": "Final answer", "usage": None},
        ]

    def test_threads_chat_context_and_sly_data_forward_like_send(self):
        session = _make_streaming_session()
        list(session.send_streaming("hello"))
        assert session.chat_context == {"ctx": 1}
        assert session.sly_data == {"sly": 1}
        assert session.input_processor.reset_called is True

    def test_skips_empty_progress_heartbeat(self):
        session = _make_streaming_session()
        events = list(session.send_streaming("hello"))
        # Only ONE progress event -- the heartbeat (empty text, no
        # structure, type "progress") must not produce a second one.
        progress_events = [e for e in events if e["status"] == "progress"]
        assert len(progress_events) == 1

    def test_no_duplicate_delta_for_an_unchanged_compiled_answer(self):
        class _RepeatingSession:
            def streaming_chat(self, chat_request):
                yield {"response": {"type": "answer", "origin": [], "text": "Same answer"}}
                yield {"response": {"type": "answer", "origin": [], "text": "Same answer"}}

        session = cli.ChatSession.__new__(cli.ChatSession)
        session.sly_data = None
        session.chat_context = None
        session.session = _RepeatingSession()
        session.input_processor = _StubStreamingInputProcessor()

        events = list(session.send_streaming("hello"))
        delta_events = [e for e in events if e["status"] == "delta"]
        assert len(delta_events) == 1  # the second, identical message is not re-emitted


class TestChatStreamRoute:
    """POST /chat/stream -- the Flask route wrapping ChatSession.send_streaming."""

    def _build_client(self, monkeypatch, send_streaming_events):
        class _StubChatSession:
            def __init__(self, agent_name, isolated=False):
                self.agent_name = agent_name

            def send_streaming(self, text):
                yield from send_streaming_events

        monkeypatch.setattr(cli, "ChatSession", _StubChatSession)
        with cli._web_sessions_lock:
            cli._web_sessions.clear()
        app = cli.build_web_app("process_architect", https=False)
        return app.test_client()

    def _parse_sse_events(self, body: str):
        import json

        return [
            json.loads(line[len("data: "):])
            for line in body.strip().split("\n\n")
            if line.startswith("data: ")
        ]

    def test_stream_emits_sse_events_ending_in_done(self, monkeypatch):
        client = self._build_client(monkeypatch, [
            {"status": "progress", "origin": "cloudarch", "text": "working..."},
            {"status": "delta", "text": "partial"},
            {"status": "delta", "text": "final text"},
            {"status": "done", "response": "final text"},
        ])
        resp = client.post("/chat/stream", json={"query": "hello"})
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")

        events = self._parse_sse_events(resp.get_data(as_text=True))
        assert [e["status"] for e in events] == ["progress", "delta", "delta", "done"]
        assert events[-1]["response"] == "final text"
        # Every event carries the same session_id, added by the route
        # itself (send_streaming's own events don't include one).
        session_ids = {e["session_id"] for e in events}
        assert len(session_ids) == 1

    def test_stream_requires_a_nonempty_query(self, monkeypatch):
        client = self._build_client(monkeypatch, [])
        resp = client.post("/chat/stream", json={})
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_stream_sets_the_session_cookie(self, monkeypatch):
        client = self._build_client(monkeypatch, [{"status": "done", "response": "hi"}])
        resp = client.post("/chat/stream", json={"query": "hello"})
        assert cli.WEB_SESSION_COOKIE in resp.headers.get("Set-Cookie", "")

    def test_stream_surfaces_an_in_band_error_event_without_crashing(self, monkeypatch):
        class _ExplodingChatSession:
            def __init__(self, agent_name, isolated=False):
                pass

            def send_streaming(self, text):
                yield {"status": "progress", "origin": "x", "text": "starting"}
                raise RuntimeError("boom")

        monkeypatch.setattr(cli, "ChatSession", _ExplodingChatSession)
        with cli._web_sessions_lock:
            cli._web_sessions.clear()
        app = cli.build_web_app("process_architect", https=False)
        client = app.test_client()

        resp = client.post("/chat/stream", json={"query": "hello"})
        assert resp.status_code == 200  # headers already sent -- error must be in-band, not an HTTP 500
        events = self._parse_sse_events(resp.get_data(as_text=True))
        assert events[0]["status"] == "progress"
        assert events[-1]["status"] == "error"

    def test_stream_requires_auth_when_configured(self, monkeypatch):
        monkeypatch.setenv("WEBAPIKEY", "secret")
        client = self._build_client(monkeypatch, [{"status": "done", "response": "hi"}])
        resp = client.post("/chat/stream", json={"query": "hello"})
        assert resp.status_code == 401


class TestChatStopRoute:
    """POST /chat/<session_id>/stop -- cancels an in-flight turn by
    reaching into the underlying DirectAgentSession's own AsyncioExecutor
    (self.session.invocation_context.get_asyncio_executor().
    cancel_current_tasks()). Stubs out the session/invocation_context/
    executor chain (same stubbing style as the rest of this file) to test
    chat_stop's OWN logic in isolation -- neuro-san's own
    cancel_current_tasks is that library's code, not this project's, and
    is out of scope here."""

    def _build_client(self, monkeypatch, known_session=None):
        with cli._web_sessions_lock:
            cli._web_sessions.clear()
            if known_session is not None:
                cli._web_sessions["known-session"] = known_session
        app = cli.build_web_app("process_architect", https=False)
        return app.test_client()

    def test_stop_when_session_is_unknown(self, monkeypatch):
        client = self._build_client(monkeypatch)
        resp = client.post("/chat/unknown-session/stop")
        assert resp.status_code == 200
        assert resp.get_json() == {
            "status": "ok", "session_id": "unknown-session", "stopped": False
        }

    def test_stop_when_no_turn_has_ever_started(self, monkeypatch):
        session = SimpleNamespace(session=SimpleNamespace(invocation_context=None))
        client = self._build_client(monkeypatch, known_session=session)
        resp = client.post("/chat/known-session/stop")
        assert resp.status_code == 200
        assert resp.get_json()["stopped"] is False

    def test_stop_cancels_via_the_asyncio_executor(self, monkeypatch):
        calls = []

        class _Executor:
            def cancel_current_tasks(self, timeout):
                calls.append(timeout)

        invocation_context = SimpleNamespace(get_asyncio_executor=lambda: _Executor())
        session = SimpleNamespace(session=SimpleNamespace(invocation_context=invocation_context))
        client = self._build_client(monkeypatch, known_session=session)

        resp = client.post("/chat/known-session/stop")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok", "session_id": "known-session", "stopped": True}
        assert calls == [5.0]

    def test_stop_treats_a_not_running_loop_as_nothing_to_stop(self, monkeypatch):
        class _Executor:
            def cancel_current_tasks(self, timeout):
                raise RuntimeError("Loop must be running to cancel remaining tasks")

        invocation_context = SimpleNamespace(get_asyncio_executor=lambda: _Executor())
        session = SimpleNamespace(session=SimpleNamespace(invocation_context=invocation_context))
        client = self._build_client(monkeypatch, known_session=session)

        resp = client.post("/chat/known-session/stop")
        assert resp.status_code == 200
        assert resp.get_json()["stopped"] is False

    def test_stop_requires_auth_when_configured(self, monkeypatch):
        monkeypatch.setenv("WEBAPIKEY", "secret")
        client = self._build_client(monkeypatch)
        resp = client.post("/chat/known-session/stop")
        assert resp.status_code == 401


class TestArtifactRoute:
    """GET /artifacts/<name> -- read-only access to output/process_data.json
    /output/design_data.json for the web client's "Process / Design" tab.
    _PROJECT_ROOT is monkeypatched to an isolated tmp_path for every test
    here so these don't depend on (or disturb) this checkout's own real
    output/ directory, whose contents vary run to run."""

    def _build_client(self, monkeypatch, tmp_path, files=None):
        monkeypatch.setattr(cli, "_PROJECT_ROOT", str(tmp_path))
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        for name, content in (files or {}).items():
            (output_dir / name).write_text(content, encoding="utf-8")
        app = cli.build_web_app("process_architect", https=False)
        return app.test_client()

    def test_returns_parsed_json_when_the_file_exists(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"process_data.json": '{"foo": "bar"}'})
        resp = client.get("/artifacts/process")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok", "name": "process", "data": {"foo": "bar"}}

    def test_design_artifact_name_maps_to_design_data_json(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"design_data.json": '{"doc": true}'})
        resp = client.get("/artifacts/design")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == {"doc": True}

    def test_404_when_the_file_has_not_been_generated_yet(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        resp = client.get("/artifacts/process")
        assert resp.status_code == 404
        assert resp.get_json()["status"] == "error"

    def test_400_for_an_unrecognized_artifact_name(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        resp = client.get("/artifacts/bogus")
        assert resp.status_code == 400

    def test_500_for_unparseable_json_on_disk(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"process_data.json": "{not valid json"})
        resp = client.get("/artifacts/process")
        assert resp.status_code == 500

    def test_requires_auth_when_configured(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WEBAPIKEY", "secret")
        client = self._build_client(monkeypatch, tmp_path, {"process_data.json": "{}"})
        resp = client.get("/artifacts/process")
        assert resp.status_code == 401

    def test_status_probe_still_bypasses_auth(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WEBAPIKEY", "secret")
        client = self._build_client(monkeypatch, tmp_path)
        resp = client.get("/status")
        assert resp.status_code == 200
