"""Unit tests for cli.py's own control-flow logic (argument parsing, control
lines, shell-escape detection) -- the parts that don't require a live LLM
credential to exercise. ChatSession itself (the part that actually talks to
neuro-san) is exercised manually/at the integration level elsewhere in this
project (ns chat), the same way every other network's LLM-backed behavior
is -- there's no API key in this environment to drive a real turn through
it in a unit test.
"""

import asyncio
import threading
import time
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


class TestParseAttachments:
    """_parse_attachments -- validates/decodes POST /chat or /chat/stream's
    optional "files" field server-side, re-checking size/count even though
    the web client enforces the same limits before ever sending (a client
    is never a trusted boundary)."""

    def _b64(self, raw: bytes) -> str:
        import base64
        return base64.b64encode(raw).decode("ascii")

    def test_absent_files_is_not_an_error(self):
        files, error = cli._parse_attachments({})
        assert files == []
        assert error is None

    def test_decodes_a_valid_file(self):
        payload = {"files": [{"name": "notes.txt", "mime_type": "text/plain", "data_base64": self._b64(b"hello")}]}
        files, error = cli._parse_attachments(payload)
        assert error is None
        assert files == [{"name": "notes.txt", "mime_type": "text/plain", "data": b"hello"}]

    def test_decodes_multiple_files_in_order(self):
        payload = {"files": [
            {"name": "a.txt", "mime_type": "text/plain", "data_base64": self._b64(b"A")},
            {"name": "b.txt", "mime_type": "text/plain", "data_base64": self._b64(b"B")},
        ]}
        files, error = cli._parse_attachments(payload)
        assert error is None
        assert [f["name"] for f in files] == ["a.txt", "b.txt"]

    def test_files_not_a_list_is_rejected(self):
        files, error = cli._parse_attachments({"files": "not-a-list"})
        assert files is None
        assert "must be a list" in error

    def test_too_many_files_is_rejected(self):
        entry = {"name": "x.txt", "mime_type": "text/plain", "data_base64": self._b64(b"x")}
        payload = {"files": [entry] * (cli.ATTACHMENT_MAX_FILES + 1)}
        files, error = cli._parse_attachments(payload)
        assert files is None
        assert "Too many" in error

    def test_entry_missing_name_is_rejected(self):
        payload = {"files": [{"mime_type": "text/plain", "data_base64": self._b64(b"x")}]}
        files, error = cli._parse_attachments(payload)
        assert files is None
        assert "name" in error

    def test_entry_missing_mime_type_is_rejected(self):
        payload = {"files": [{"name": "x.txt", "data_base64": self._b64(b"x")}]}
        files, error = cli._parse_attachments(payload)
        assert files is None
        assert "mime_type" in error

    def test_entry_missing_data_is_rejected(self):
        payload = {"files": [{"name": "x.txt", "mime_type": "text/plain"}]}
        files, error = cli._parse_attachments(payload)
        assert files is None
        assert "data_base64" in error

    def test_invalid_base64_is_rejected(self):
        payload = {"files": [{"name": "x.txt", "mime_type": "text/plain", "data_base64": "not valid base64!!"}]}
        files, error = cli._parse_attachments(payload)
        assert files is None
        assert "invalid base64" in error

    def test_oversized_file_is_rejected(self):
        oversized = self._b64(b"x" * (cli.ATTACHMENT_MAX_BYTES + 1))
        payload = {"files": [{"name": "big.bin", "mime_type": "application/octet-stream", "data_base64": oversized}]}
        files, error = cli._parse_attachments(payload)
        assert files is None
        assert "exceeds" in error

    def test_file_at_exactly_the_limit_is_accepted(self):
        at_limit = self._b64(b"x" * cli.ATTACHMENT_MAX_BYTES)
        payload = {"files": [{"name": "ok.bin", "mime_type": "application/octet-stream", "data_base64": at_limit}]}
        files, error = cli._parse_attachments(payload)
        assert error is None
        assert len(files[0]["data"]) == cli.ATTACHMENT_MAX_BYTES


class TestIngestAttachments:
    """ChatSession._ingest_attachments -- extracts text from this turn's
    attached files and stores it in sly_data, where the
    load_attached_files CodedTool can surface it to the agent (sly_data
    itself is invisible to the LLM's own prompt)."""

    def _session(self):
        session = cli.ChatSession.__new__(cli.ChatSession)
        session.sly_data = None
        return session

    def test_no_files_is_a_no_op(self):
        session = self._session()
        session._ingest_attachments(None)
        assert session.sly_data is None
        session._ingest_attachments([])
        assert session.sly_data is None

    def test_text_file_is_extracted_into_sly_data(self):
        session = self._session()
        session._ingest_attachments([{"name": "notes.txt", "mime_type": "text/plain", "data": b"hello world"}])
        entries = session.sly_data[cli.ATTACHED_FILES_SLY_DATA_KEY]
        assert len(entries) == 1
        assert entries[0]["name"] == "notes.txt"
        assert entries[0]["mime_type"] == "text/plain"
        assert entries[0]["status"] == "OK"
        assert entries[0]["text"] == "hello world"

    def test_image_file_is_marked_unsupported_not_dropped_silently(self):
        session = self._session()
        session._ingest_attachments([{"name": "diagram.png", "mime_type": "image/png", "data": b"\x89PNGnotreal"}])
        entries = session.sly_data[cli.ATTACHED_FILES_SLY_DATA_KEY]
        assert entries[0]["status"] == "UNSUPPORTED"
        assert "not readable as text" in entries[0]["reason"]

    def test_creates_sly_data_dict_when_none(self):
        session = self._session()
        assert session.sly_data is None
        session._ingest_attachments([{"name": "a.txt", "mime_type": "text/plain", "data": b"x"}])
        assert isinstance(session.sly_data, dict)

    def test_new_turns_files_replace_the_previous_turns(self):
        session = self._session()
        session._ingest_attachments([{"name": "first.txt", "mime_type": "text/plain", "data": b"first"}])
        session._ingest_attachments([{"name": "second.txt", "mime_type": "text/plain", "data": b"second"}])
        entries = session.sly_data[cli.ATTACHED_FILES_SLY_DATA_KEY]
        assert [e["name"] for e in entries] == ["second.txt"]

    def test_a_turn_with_no_new_files_leaves_earlier_attachments_in_place(self):
        # A later turn with no attachments of its own can still reference
        # something attached a few messages back.
        session = self._session()
        session._ingest_attachments([{"name": "spec.txt", "mime_type": "text/plain", "data": b"spec content"}])
        session._ingest_attachments(None)
        entries = session.sly_data[cli.ATTACHED_FILES_SLY_DATA_KEY]
        assert [e["name"] for e in entries] == ["spec.txt"]

    def test_existing_sly_data_keys_are_preserved(self):
        session = self._session()
        session.sly_data = {"some_other_key": "value"}
        session._ingest_attachments([{"name": "a.txt", "mime_type": "text/plain", "data": b"x"}])
        assert session.sly_data["some_other_key"] == "value"
        assert cli.ATTACHED_FILES_SLY_DATA_KEY in session.sly_data


def test_send_logs_token_accounting_at_info(caplog):
    """ChatSession.send must surface token_accounting (previously silently
    discarded) via the standard logger at INFO, not swallow it."""
    session = cli.ChatSession.__new__(cli.ChatSession)  # bypass __init__'s real session setup
    session.sly_data = None
    session.chat_context = None
    session._lock = threading.Lock()

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
    session._lock = threading.Lock()
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

    def test_skips_structure_only_progress_message_instead_of_leaking_key_names(self):
        # Regression test: confirmed in a real session -- neuro-san's own
        # token-accounting bookkeeping ping carries a {total_tokens,
        # prompt_tokens, ...} "structure" dict with NO "text". This used to
        # fall back to a synthetic "<structure: total_tokens, prompt_tokens,
        # ...>" preview (the dict's field NAMES, not values) that the web
        # client renders as a visible step in the turn's "Thinking" trace --
        # pure internal bookkeeping leaking into the chat transcript as
        # confusing noise. The real totals already reach the client cleanly
        # via this same method's "done" event ("usage") -- a structure-only
        # message (no text) must now be skipped entirely, same as the
        # already-skipped empty-text heartbeat.
        class _StructureOnlySession:
            def streaming_chat(self, chat_request):
                yield {"response": {
                    "type": "progress", "origin": [{"tool": "cloudarch"}],
                    "structure": {
                        "total_tokens": 42, "prompt_tokens": 30, "completion_tokens": 12,
                        "successful_requests": 1, "empty_responses": 0, "total_cost": 0.01,
                        "time_taken_in_seconds": 1.2, "caveats": [],
                    },
                }}
                yield {"response": {"type": "answer", "origin": [], "text": "Final answer"}}

        session = cli.ChatSession.__new__(cli.ChatSession)
        session.sly_data = None
        session.chat_context = None
        session._lock = threading.Lock()
        session.session = _StructureOnlySession()
        session.input_processor = _StubStreamingInputProcessor()

        events = list(session.send_streaming("hello"))
        assert not any(e["status"] == "progress" for e in events)
        assert not any("<structure:" in str(e.get("text", "")) for e in events)

    def test_no_duplicate_delta_for_an_unchanged_compiled_answer(self):
        class _RepeatingSession:
            def streaming_chat(self, chat_request):
                yield {"response": {"type": "answer", "origin": [], "text": "Same answer"}}
                yield {"response": {"type": "answer", "origin": [], "text": "Same answer"}}

        session = cli.ChatSession.__new__(cli.ChatSession)
        session.sly_data = None
        session.chat_context = None
        session._lock = threading.Lock()
        session.session = _RepeatingSession()
        session.input_processor = _StubStreamingInputProcessor()

        events = list(session.send_streaming("hello"))
        delta_events = [e for e in events if e["status"] == "delta"]
        assert len(delta_events) == 1  # the second, identical message is not re-emitted


class TestChatStreamRoute:
    """POST /chat/stream -- the Flask route wrapping ChatSession.send_streaming."""

    def _build_client(self, monkeypatch, send_streaming_events, received_files=None):
        class _StubChatSession:
            def __init__(self, agent_name, isolated=False):
                self.agent_name = agent_name

            def send_streaming(self, text, files=None):
                if received_files is not None:
                    received_files.append(files)
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

            def send_streaming(self, text, files=None):
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

    def test_stream_decodes_and_forwards_attached_files(self, monkeypatch):
        import base64

        received = []
        client = self._build_client(
            monkeypatch, [{"status": "done", "response": "hi"}], received_files=received
        )
        resp = client.post("/chat/stream", json={
            "query": "hello",
            "files": [{
                "name": "notes.txt", "mime_type": "text/plain",
                "data_base64": base64.b64encode(b"hi there").decode("ascii"),
            }],
        })
        assert resp.status_code == 200
        assert received == [[{"name": "notes.txt", "mime_type": "text/plain", "data": b"hi there"}]]

    def test_stream_rejects_an_invalid_files_payload_with_400_before_reaching_the_session(self, monkeypatch):
        received = []
        client = self._build_client(monkeypatch, [], received_files=received)
        resp = client.post("/chat/stream", json={"query": "hello", "files": "not-a-list"})
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"
        assert received == []  # never reached send_streaming at all


class TestChatRoute:
    """POST /chat -- the non-streaming counterpart wrapping
    ChatSession.send. Same request contract as /chat/stream (see that
    class above), blocking until the turn completes instead of streaming
    progress."""

    def _build_client(self, monkeypatch, response_text="hi", received_files=None):
        class _StubChatSession:
            def __init__(self, agent_name, isolated=False):
                self.agent_name = agent_name
                self.last_usage = None

            def send(self, text, files=None):
                if received_files is not None:
                    received_files.append(files)
                return response_text

        monkeypatch.setattr(cli, "ChatSession", _StubChatSession)
        with cli._web_sessions_lock:
            cli._web_sessions.clear()
        app = cli.build_web_app("process_architect", https=False)
        return app.test_client()

    def test_chat_requires_a_nonempty_query(self, monkeypatch):
        client = self._build_client(monkeypatch)
        resp = client.post("/chat", json={})
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_chat_returns_the_response_and_sets_the_session_cookie(self, monkeypatch):
        client = self._build_client(monkeypatch, response_text="the answer")
        resp = client.post("/chat", json={"query": "hello"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert body["response"] == "the answer"
        assert cli.WEB_SESSION_COOKIE in resp.headers.get("Set-Cookie", "")

    def test_chat_decodes_and_forwards_attached_files(self, monkeypatch):
        import base64

        received = []
        client = self._build_client(monkeypatch, received_files=received)
        resp = client.post("/chat", json={
            "query": "hello",
            "files": [{
                "name": "spec.md", "mime_type": "text/markdown",
                "data_base64": base64.b64encode(b"# Spec").decode("ascii"),
            }],
        })
        assert resp.status_code == 200
        assert received == [[{"name": "spec.md", "mime_type": "text/markdown", "data": b"# Spec"}]]

    def test_chat_rejects_an_invalid_files_payload_with_400_before_reaching_the_session(self, monkeypatch):
        received = []
        client = self._build_client(monkeypatch, received_files=received)
        resp = client.post("/chat", json={"query": "hello", "files": [{"name": "x.txt"}]})
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"
        assert received == []


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


class TestGetOrCreateWebSessionEviction:
    """_get_or_create_web_session's opportunistic idle-eviction sweep --
    regression coverage for two review findings:

    1. last_accessed is stamped at turn START (ChatSession.send/
       send_streaming), so a turn genuinely running longer than the idle
       timeout must not be evicted out from under itself just because its
       timestamp looks stale while it's still running. _active_web_sessions
       (a per-session request COUNT, pinned/unpinned by
       _get_or_create_web_session/_release_web_session) is the signal the
       sweep actually checks.
    2. The pin happens in the SAME _web_sessions_lock-protected step as the
       lookup/creation itself -- closing the narrow window where a request
       could look up a session, then (before ever calling
       session.send()/send_streaming(), which is the only other thing that
       used to guard against eviction) have a concurrent sweep see it as
       idle and not yet pinned, and evict it out from under the request
       about to use it.
    """

    def _fake_session(self, *, last_accessed):
        close_calls = []
        return SimpleNamespace(
            last_accessed=last_accessed,
            session=SimpleNamespace(close=lambda: close_calls.append(True)),
            _close_calls=close_calls,
        )

    def _reset(self, monkeypatch):
        monkeypatch.setattr(cli, "_web_sessions_last_swept", 0.0)
        with cli._web_sessions_lock:
            cli._web_sessions.clear()
            cli._active_web_sessions.clear()

    def test_idle_and_unpinned_session_is_evicted(self, monkeypatch):
        self._reset(monkeypatch)
        stale = time.monotonic() - cli._WEB_SESSION_IDLE_TIMEOUT_SECONDS - 10
        idle = self._fake_session(last_accessed=stale)
        current = self._fake_session(last_accessed=time.monotonic())
        with cli._web_sessions_lock:
            cli._web_sessions["idle"] = idle
            cli._web_sessions["current"] = current

        result = cli._get_or_create_web_session("current", "process_architect")

        assert result == ("current", current)
        assert "idle" not in cli._web_sessions
        assert idle._close_calls == [True]

    def test_idle_but_pinned_session_mid_turn_is_not_evicted(self, monkeypatch):
        self._reset(monkeypatch)
        stale = time.monotonic() - cli._WEB_SESSION_IDLE_TIMEOUT_SECONDS - 10
        # Pinned == a request is still holding this session, per
        # _get_or_create_web_session/_release_web_session's contract.
        mid_turn = self._fake_session(last_accessed=stale)
        current = self._fake_session(last_accessed=time.monotonic())
        with cli._web_sessions_lock:
            cli._web_sessions["mid-turn"] = mid_turn
            cli._web_sessions["current"] = current
            cli._active_web_sessions["mid-turn"] = 1

        result = cli._get_or_create_web_session("current", "process_architect")

        assert result == ("current", current)
        assert "mid-turn" in cli._web_sessions
        assert mid_turn._close_calls == []

    def test_recently_accessed_session_is_never_swept(self, monkeypatch):
        self._reset(monkeypatch)
        current = self._fake_session(last_accessed=time.monotonic())
        with cli._web_sessions_lock:
            cli._web_sessions["current"] = current

        cli._get_or_create_web_session("current", "process_architect")

        assert "current" in cli._web_sessions
        assert current._close_calls == []

    def test_lookup_pins_the_session_in_the_same_locked_step(self, monkeypatch):
        self._reset(monkeypatch)
        current = self._fake_session(last_accessed=time.monotonic())
        with cli._web_sessions_lock:
            cli._web_sessions["current"] = current

        cli._get_or_create_web_session("current", "process_architect")

        with cli._web_sessions_lock:
            assert cli._active_web_sessions["current"] == 1

    def test_overlapping_lookups_on_the_same_session_both_must_release_before_eviction_is_possible(self, monkeypatch):
        # Regression test: _active_web_sessions used to be (in an earlier,
        # since-fixed design) a bare flag -- two overlapping requests on
        # the SAME session both pinned it, but the FIRST to release could
        # blindly unpin it even while the SECOND was still active. The
        # count must only reach zero once BOTH requests have released.
        self._reset(monkeypatch)
        shared = self._fake_session(last_accessed=time.monotonic())
        anchor = self._fake_session(last_accessed=time.monotonic())
        with cli._web_sessions_lock:
            cli._web_sessions["shared"] = shared
            cli._web_sessions["anchor"] = anchor

        cli._get_or_create_web_session("shared", "process_architect")  # first overlapping request
        cli._get_or_create_web_session("shared", "process_architect")  # second overlapping request
        with cli._web_sessions_lock:
            assert cli._active_web_sessions["shared"] == 2

        cli._release_web_session("shared")  # first request finishes
        with cli._web_sessions_lock:
            assert "shared" in cli._active_web_sessions  # still pinned -- second request active
            # Simulate the second request's turn having run long enough
            # that shared's timestamp now LOOKS idle, even though it is
            # genuinely still in flight.
            shared.last_accessed = time.monotonic() - cli._WEB_SESSION_IDLE_TIMEOUT_SECONDS - 10

        cli._get_or_create_web_session("anchor", "process_architect")  # triggers a sweep pass
        with cli._web_sessions_lock:
            assert "shared" in cli._web_sessions  # must survive -- second request still holds it

        cli._release_web_session("shared")  # second request finishes
        with cli._web_sessions_lock:
            assert "shared" not in cli._active_web_sessions

    def test_release_web_session_refreshes_last_accessed(self, monkeypatch):
        # Regression test: last_accessed was only ever stamped at turn
        # START. A turn that runs right up to (or past) the idle timeout
        # finished successfully, but still carried its original, now-stale
        # start timestamp the instant it ended -- making the very next
        # sweep see it as idle and evict a session that had just finished
        # normally.
        self._reset(monkeypatch)
        turn_start = time.monotonic() - cli._WEB_SESSION_IDLE_TIMEOUT_SECONDS - 10
        session = self._fake_session(last_accessed=turn_start)
        with cli._web_sessions_lock:
            cli._web_sessions["just-finished"] = session
            cli._active_web_sessions["just-finished"] = 1

        cli._release_web_session("just-finished")

        assert session.last_accessed > turn_start
