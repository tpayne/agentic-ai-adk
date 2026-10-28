"""Unit tests for cli.py's own control-flow logic (argument parsing, control
lines, shell-escape detection) -- the parts that don't require a live LLM
credential to exercise. ChatSession itself (the part that actually talks to
neuro-san) is exercised manually/at the integration level elsewhere in this
project (ns chat), the same way every other network's LLM-backed behavior
is -- there's no API key in this environment to drive a real turn through
it in a unit test.
"""

import asyncio
import importlib
import os
import shutil
import tempfile
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

import cli
from process_toolkit import paths


@pytest.fixture(autouse=True)
def _reset_web_rate_limit_state():
    # cli._web_rate_limit_state is module-level and otherwise never
    # cleared between tests -- every Flask-route test in this file shares
    # the same client_key (Flask's test client always uses the same fake
    # remote_addr), so without this, enough tests accumulated across a
    # full run of this file trip WEBRATELIMITPERMINUTE's default of
    # 30/minute by sheer count, producing a spurious 429 in whichever
    # test happens to be running when the threshold is crossed -- unrelated
    # to what that test is actually checking.
    with cli._web_rate_limit_lock:
        cli._web_rate_limit_state.clear()
    yield


def test_agent_tool_path_and_manifest_are_forced_to_this_project_even_if_already_set(monkeypatch):
    # Regression test: a prior `ns chat`/`ns run` session (or another
    # neuro-san project) can leave AGENT_TOOL_PATH/AGENT_MANIFEST_FILE
    # exported in the same shell -- cli.py must FORCE these to its own
    # project root rather than deferring to a stale value (setdefault would
    # silently keep it, reproducing a real "Could not find class ... under
    # AGENT_TOOL_PATH 'coded_tools'" failure confirmed against a real run).
    monkeypatch.setenv("AGENT_TOOL_PATH", "/some/other/stale/path")
    monkeypatch.setenv("AGENT_MANIFEST_FILE", "/some/other/stale/manifest.hocon")
    importlib.reload(cli)
    assert os.environ["AGENT_TOOL_PATH"] == os.path.join(cli._PROJECT_ROOT, "coded_tools")
    assert os.environ["AGENT_MANIFEST_FILE"] == os.path.join(
        cli._PROJECT_ROOT, "registries", "manifest.hocon"
    )


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


class TestListAndDownloadControlLines:
    """"list"/"ls" and "download <filename> [destination]" -- neither
    hits the agent at all (a plain local directory listing / file copy
    against this project's own output/, since the interactive/-f CLI
    already runs in-process on this filesystem -- no server round trip
    needed, unlike the web client's own download buttons)."""

    def test_list_does_not_hit_the_agent(self, monkeypatch, tmp_path):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        holder = [_StubSession()]
        should_stop = asyncio.run(cli.handle_logical_line("list", holder, "process_architect"))
        assert should_stop is False
        assert holder[0].sent == []

    def test_list_reports_no_documents_yet_when_output_is_empty(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        asyncio.run(cli.handle_logical_line("list", [_StubSession()], "process_architect"))
        assert "No generated documents yet" in capsys.readouterr().out

    def test_list_shows_generated_docx_and_cloudarch_xml(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "Vendor_Onboarding.docx").write_bytes(b"fake docx")
        (output_dir / "cloudarch_drawio.xml").write_text("<mxfile></mxfile>", encoding="utf-8")
        asyncio.run(cli.handle_logical_line("list", [_StubSession()], "process_architect"))
        out = capsys.readouterr().out
        assert "Vendor_Onboarding.docx" in out
        assert "cloudarch_drawio.xml" in out

    def test_download_copies_the_file_to_the_given_destination(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "Vendor_Onboarding.docx").write_bytes(b"fake docx bytes")
        dest_dir = tmp_path / "downloads"
        dest_dir.mkdir()
        holder = [_StubSession()]

        should_stop = asyncio.run(
            cli.handle_logical_line(f"download Vendor_Onboarding.docx {dest_dir}", holder, "process_architect")
        )

        assert should_stop is False
        assert holder[0].sent == []  # never reached the agent
        copied = dest_dir / "Vendor_Onboarding.docx"
        assert copied.read_bytes() == b"fake docx bytes"
        assert "Downloaded" in capsys.readouterr().out

    def test_download_defaults_to_the_current_working_directory(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "Vendor_Onboarding.docx").write_bytes(b"fake docx bytes")
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        monkeypatch.chdir(cwd_dir)

        asyncio.run(cli.handle_logical_line("download Vendor_Onboarding.docx", [_StubSession()], "process_architect"))

        assert (cwd_dir / "Vendor_Onboarding.docx").read_bytes() == b"fake docx bytes"

    def test_download_reports_an_error_for_an_unknown_filename(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        (tmp_path / "output").mkdir()
        asyncio.run(cli.handle_logical_line("download nonexistent.docx", [_StubSession()], "process_architect"))
        assert "No generated file named 'nonexistent.docx'" in capsys.readouterr().out

    def test_download_rejects_a_path_traversal_attempt(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        (tmp_path / "output").mkdir()
        (tmp_path / "secret.txt").write_text("do not leak me", encoding="utf-8")
        asyncio.run(
            cli.handle_logical_line("download ../secret.txt", [_StubSession()], "process_architect")
        )
        out = capsys.readouterr().out
        assert "No generated file named" in out

    def test_download_with_no_filename_shows_usage(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        asyncio.run(cli.handle_logical_line("download", [_StubSession()], "process_architect"))
        assert "Usage: download" in capsys.readouterr().out


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
    web client's Token Usage tab expects (same keys the ADK port's own
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
    """ChatSession._ingest_attachments -- stages this turn's attached
    files into this session's FIXED on-disk directory
    (self._attachments_directory, set once in __init__) and returns that
    directory's path so send()/send_streaming() can append it to the
    user's own message text as a literal "[ATTACHMENT DIRECTORY: ...]"
    marker (see _append_attachment_directory_marker) -- no sly_data, no
    dedicated CodedTool; the agent picks it up through its existing
    "request explicitly names a directory" handling."""

    def _session(self):
        session = cli.ChatSession.__new__(cli.ChatSession)
        session.sly_data = None
        session._attachments_directory = os.path.join(
            tempfile.gettempdir(), f"test_attachments_{uuid.uuid4().hex}",
        )
        return session

    def _cleanup(self, session):
        shutil.rmtree(session._attachments_directory, ignore_errors=True)

    def test_no_files_is_a_no_op(self):
        session = self._session()
        assert session._ingest_attachments(None) is None
        assert not os.path.exists(session._attachments_directory)
        assert session._ingest_attachments([]) is None
        assert not os.path.exists(session._attachments_directory)

    def test_text_file_is_staged_to_the_fixed_directory(self):
        from pathlib import Path

        session = self._session()
        try:
            returned = session._ingest_attachments(
                [{"name": "notes.txt", "mime_type": "text/plain", "data": b"hello world"}]
            )
            assert returned == session._attachments_directory
            assert (Path(session._attachments_directory) / "notes.txt").read_bytes() == b"hello world"
        finally:
            self._cleanup(session)

    def test_new_turns_files_replace_the_previous_turns_in_the_same_directory(self):
        from pathlib import Path

        session = self._session()
        try:
            session._ingest_attachments([{"name": "first.txt", "mime_type": "text/plain", "data": b"first"}])
            session._ingest_attachments([{"name": "second.txt", "mime_type": "text/plain", "data": b"second"}])

            remaining = [p.name for p in Path(session._attachments_directory).iterdir()]
            assert remaining == ["second.txt"]
        finally:
            self._cleanup(session)

    def test_a_turn_with_no_new_files_returns_none_but_leaves_earlier_files_in_place(self):
        # A later turn with no attachments of its own can still reference
        # something attached a few messages back, by name, without
        # re-attaching it -- but it must NOT get a fresh
        # "[ATTACHMENT DIRECTORY: ...]" marker appended to ITS OWN text
        # just because an earlier turn attached something.
        from pathlib import Path

        session = self._session()
        try:
            session._ingest_attachments([{"name": "spec.txt", "mime_type": "text/plain", "data": b"spec content"}])
            returned = session._ingest_attachments(None)
            assert returned is None
            assert (Path(session._attachments_directory) / "spec.txt").read_bytes() == b"spec content"
        finally:
            self._cleanup(session)

    def test_staging_failure_raises_instead_of_silently_dropping_the_attachment(self, monkeypatch):
        # A silently-ignored staging failure would be worse than a loud
        # one: the user believes their attachment was used, nothing in
        # the response says otherwise, and the agent just works from
        # whatever text they typed instead.
        monkeypatch.setattr(
            cli, "stage_attachments_to_directory",
            lambda files, directory: {"status": "ERROR", "error": "disk full"},
        )
        session = self._session()
        with pytest.raises(RuntimeError, match="disk full"):
            session._ingest_attachments([{"name": "a.txt", "mime_type": "text/plain", "data": b"x"}])


class TestAppendAttachmentDirectoryMarker:
    """_append_attachment_directory_marker -- the one place the staged
    directory's path becomes visible, literal text in the user's own
    message, instead of an invisible sly_data side channel."""

    def test_none_directory_leaves_text_unchanged(self):
        assert cli._append_attachment_directory_marker("hello", None) == "hello"

    def test_directory_is_appended_as_a_marker_line(self):
        result = cli._append_attachment_directory_marker("create a process", "/tmp/xyz")
        assert result == "create a process\n\n[ATTACHMENT DIRECTORY: /tmp/xyz]"

    def test_empty_text_becomes_just_the_marker(self):
        # cli.py's own /chat and /chat/stream routes already require a
        # non-empty "query", but this helper is defensive regardless --
        # no leading blank lines if "text" ever is empty.
        result = cli._append_attachment_directory_marker("", "/tmp/xyz")
        assert result == "[ATTACHMENT DIRECTORY: /tmp/xyz]"


class TestChatSessionClose:
    """ChatSession.close() -- must release both the attachment-staging
    directory and the underlying neuro-san session, since it's called
    from both the idle-eviction sweep and DELETE /chat/<session_id>."""

    def _session(self):
        session = cli.ChatSession.__new__(cli.ChatSession)
        session.sly_data = None
        session.session = SimpleNamespace(close=lambda: None)
        session._attachments_directory = os.path.join(
            tempfile.gettempdir(), f"test_attachments_{uuid.uuid4().hex}",
        )
        return session

    def test_close_removes_the_staging_directory_from_disk(self):
        from pathlib import Path

        session = self._session()
        session._ingest_attachments([{"name": "a.txt", "mime_type": "text/plain", "data": b"x"}])
        directory = session._attachments_directory
        assert Path(directory).is_dir()

        session.close()
        assert not Path(directory).exists()

    def test_close_is_a_no_op_on_the_filesystem_when_nothing_was_attached(self):
        session = self._session()
        session.close()  # must not raise just because there's nothing to clean up

    def test_close_always_closes_the_underlying_neuro_san_session(self):
        closed = []
        session = self._session()
        session.session = SimpleNamespace(close=lambda: closed.append(True))
        session.close()
        assert closed == [True]


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


class TestChatDeleteRoute:
    """DELETE /chat/<session_id> -- drops server-side state for a
    session, calling ChatSession.close() (not session.session.close()
    directly) so the attachment-staging directory is released alongside
    the underlying neuro-san session."""

    def _build_client(self, monkeypatch, known_session=None):
        with cli._web_sessions_lock:
            cli._web_sessions.clear()
            if known_session is not None:
                cli._web_sessions["known-session"] = known_session
        app = cli.build_web_app("process_architect", https=False)
        return app.test_client()

    def test_delete_of_unknown_session_reports_not_cleared(self, monkeypatch):
        client = self._build_client(monkeypatch)
        resp = client.delete("/chat/unknown-session")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok", "session_id": "unknown-session", "cleared": False}

    def test_delete_of_known_session_calls_close_and_reports_cleared(self, monkeypatch):
        close_calls = []
        session = SimpleNamespace(close=lambda: close_calls.append(True))
        client = self._build_client(monkeypatch, known_session=session)

        resp = client.delete("/chat/known-session")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok", "session_id": "known-session", "cleared": True}
        assert close_calls == [True]
        assert "known-session" not in cli._web_sessions

    def test_delete_logs_but_does_not_fail_when_close_raises(self, monkeypatch):
        def _boom():
            raise RuntimeError("neuro-san session already closed")

        session = SimpleNamespace(close=_boom)
        client = self._build_client(monkeypatch, known_session=session)

        resp = client.delete("/chat/known-session")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok", "session_id": "known-session", "cleared": True}


class TestChatSessionOutputIsolation:
    """Multi-session output isolation: two concurrent /chat sessions must
    never write into (or be able to read) each other's output/<session_id>/
    files, and DELETE /chat/<session_id> must remove that session's own
    directory immediately rather than waiting for the next purge sweep."""

    def _build_client(self, monkeypatch):
        """Returns the built Flask app (not a test_client()) -- callers
        that need multiple independent cookie jars call .test_client()
        themselves, once per simulated "browser"."""

        class _StubChatSession:
            """Stands in for a real ChatSession whose underlying pipeline
            tools write real files via process_toolkit.paths -- send()
            here does the same, so this test exercises the ACTUAL
            paths.use_session() wiring in cli.py's own chat()/chat_stream(),
            not just a mock that bypasses it entirely."""

            def __init__(self, agent_name, isolated=False):
                self.agent_name = agent_name
                self.last_usage = None

            def send(self, text, files=None):
                path = paths.output_path("process_data.json")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                return path

        monkeypatch.setattr(cli, "ChatSession", _StubChatSession)
        with cli._web_sessions_lock:
            cli._web_sessions.clear()
            cli._active_web_sessions.clear()
        return cli.build_web_app("process_architect", https=False)

    def test_two_sessions_write_to_different_output_directories(self, monkeypatch):
        app = self._build_client(monkeypatch)
        # Two SEPARATE test_client() instances -- each has its own
        # independent cookie jar, so neither resends the other's
        # Set-Cookie session id, unlike reusing one client for both calls
        # (Flask's test client persists cookies across requests on the
        # SAME client, which would make the second call reuse the first
        # call's session -- confirmed by this test initially failing that
        # way).
        client_a = app.test_client()
        client_b = app.test_client()

        resp_a = client_a.post("/chat", json={"query": "session A's data"})
        session_a = resp_a.get_json()["session_id"]
        path_a = resp_a.get_json()["response"]

        resp_b = client_b.post("/chat", json={"query": "session B's data"})
        session_b = resp_b.get_json()["session_id"]
        path_b = resp_b.get_json()["response"]

        assert session_a != session_b
        assert path_a != path_b
        assert session_a in path_a
        assert session_b in path_b
        with open(path_a, encoding="utf-8") as f:
            assert f.read() == "session A's data"
        with open(path_b, encoding="utf-8") as f:
            assert f.read() == "session B's data"

    def test_delete_removes_the_sessions_output_directory_immediately(self, monkeypatch):
        client = self._build_client(monkeypatch).test_client()

        resp = client.post("/chat", json={"query": "will be deleted"})
        session_id = resp.get_json()["session_id"]
        session_dir = os.path.join(paths.OUTPUT_DIR, session_id)
        assert os.path.isdir(session_dir)

        client.delete(f"/chat/{session_id}")

        assert not os.path.isdir(session_dir)


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
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
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

    def test_cloudarch_artifact_name_maps_to_cloudarch_drawio_xml_and_returns_raw_text(self, monkeypatch, tmp_path):
        client = self._build_client(
            monkeypatch, tmp_path, {"cloudarch_drawio.xml": "<mxfile><diagram>stuff</diagram></mxfile>"}
        )
        resp = client.get("/artifacts/cloudarch")
        assert resp.status_code == 200
        assert resp.get_json() == {
            "status": "ok", "name": "cloudarch", "data": "<mxfile><diagram>stuff</diagram></mxfile>",
        }

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

    def test_a_session_scoped_file_is_found_via_the_session_id_query_param(self, monkeypatch, tmp_path):
        # Regression test: the web client tracks its own session id in JS
        # state and passes it explicitly as a query parameter on every GET
        # /artifacts/* request (it does not rely on the session cookie at
        # all -- this server's own CORS handling never sets
        # Access-Control-Allow-Credentials, so a cross-origin fetch(), the
        # web client's typical deployment, never sends or receives it
        # regardless). A file written under a session's own
        # output/<session_id>/ directory must be reachable via
        # ?session_id=<id>, not just the (unreliable, for this client)
        # cookie.
        client = self._build_client(monkeypatch, tmp_path)
        with paths.use_session("a-session-id"):
            session_output_dir = os.path.join(paths.OUTPUT_DIR, "a-session-id")
            os.makedirs(session_output_dir, exist_ok=True)
            with open(os.path.join(session_output_dir, "process_data.json"), "w", encoding="utf-8") as f:
                f.write('{"process_name": "Vendor Onboarding"}')

        resp_without = client.get("/artifacts/process")
        assert resp_without.status_code == 404  # not found via flat output/ -- it's session-scoped

        resp_with = client.get("/artifacts/process?session_id=a-session-id")
        assert resp_with.status_code == 200
        assert resp_with.get_json()["data"] == {"process_name": "Vendor Onboarding"}

    def test_session_id_query_param_is_preferred_over_the_cookie(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        with paths.use_session("query-param-session"):
            session_output_dir = os.path.join(paths.OUTPUT_DIR, "query-param-session")
            os.makedirs(session_output_dir, exist_ok=True)
            with open(os.path.join(session_output_dir, "process_data.json"), "w", encoding="utf-8") as f:
                f.write('{"process_name": "Via Query Param"}')

        client.set_cookie("process_architect_session", "a-different-cookie-session")
        resp = client.get("/artifacts/process?session_id=query-param-session")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == {"process_name": "Via Query Param"}


class TestProcessDesignJsonDownloadRoutes:
    """GET /artifacts/process/download and GET /artifacts/design/download --
    real raw-file downloads of process_data.json/design_data.json (as
    opposed to TestArtifactRoute's JSON-wrapped reads above), so a user can
    save their current process/design and later re-attach the exact same
    file to resume work -- see Process_Import_Agent/Design_Import_Agent's
    own instructions for the upload side. Mirrors download_cloudarch's own
    existing test coverage."""

    def _build_client(self, monkeypatch, tmp_path, files=None):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        for name, content in (files or {}).items():
            (output_dir / name).write_text(content, encoding="utf-8")
        app = cli.build_web_app("process_architect", https=False)
        return app.test_client()

    def test_downloads_process_data_json_as_a_real_attachment(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"process_data.json": '{"process_name": "Vendor Onboarding"}'})
        resp = client.get("/artifacts/process/download")
        assert resp.status_code == 200
        assert resp.data == b'{"process_name": "Vendor Onboarding"}'
        assert "process_data.json" in resp.headers.get("Content-Disposition", "")
        assert resp.mimetype == "application/json"

    def test_downloads_design_data_json_as_a_real_attachment(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"design_data.json": '{"document_metadata": {}}'})
        resp = client.get("/artifacts/design/download")
        assert resp.status_code == 200
        assert resp.data == b'{"document_metadata": {}}'
        assert "design_data.json" in resp.headers.get("Content-Disposition", "")

    def test_404s_when_not_yet_generated(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        assert client.get("/artifacts/process/download").status_code == 404
        assert client.get("/artifacts/design/download").status_code == 404

    def test_400_for_an_unrecognized_artifact_name(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        resp = client.get("/artifacts/bogus/download")
        assert resp.status_code == 400

    def test_cloudarch_download_still_resolves_correctly_alongside_the_new_route(self, monkeypatch, tmp_path):
        # Regression guard: /artifacts/<name>/download (new, variable segment)
        # must not shadow /artifacts/cloudarch/download (existing, literal
        # segment) -- Flask/Werkzeug should prefer the more specific static
        # route, but this proves it rather than assuming it.
        client = self._build_client(monkeypatch, tmp_path, {"cloudarch_drawio.xml": "<mxfile></mxfile>"})
        resp = client.get("/artifacts/cloudarch/download")
        assert resp.status_code == 200
        assert resp.data == b"<mxfile></mxfile>"

    def test_requires_auth_when_configured(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WEBAPIKEY", "secret")
        client = self._build_client(monkeypatch, tmp_path, {"process_data.json": "{}"})
        resp = client.get("/artifacts/process/download")
        assert resp.status_code == 401

    def test_resolves_a_session_scoped_file_via_the_session_id_query_param(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        with paths.use_session("resume-session"):
            session_output_dir = os.path.join(paths.OUTPUT_DIR, "resume-session")
            os.makedirs(session_output_dir, exist_ok=True)
            with open(os.path.join(session_output_dir, "process_data.json"), "w", encoding="utf-8") as f:
                f.write('{"process_name": "Session Scoped"}')

        assert client.get("/artifacts/process/download").status_code == 404
        resp = client.get("/artifacts/process/download?session_id=resume-session")
        assert resp.status_code == 200
        assert resp.data == b'{"process_name": "Session Scoped"}'


class TestDocumentDownloadRoutes:
    """GET /artifacts/documents (list), GET /artifacts/documents/<filename>/
    download, and GET /artifacts/cloudarch/download -- real file downloads
    for the web client's download buttons, as opposed to TestArtifactRoute's
    JSON-wrapped reads above. _PROJECT_ROOT is monkeypatched to an isolated
    tmp_path, same pattern as TestArtifactRoute."""

    def _build_client(self, monkeypatch, tmp_path, output_files=None):
        monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path / "output"))
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        for name, content in (output_files or {}).items():
            path = output_dir / name
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        app = cli.build_web_app("process_architect", https=False)
        return app.test_client()

    def test_list_documents_returns_only_docx_files(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {
            "Vendor_Onboarding.docx": b"fake docx",
            "process_data.json": "{}",
            "cloudarch_drawio.xml": "<mxfile></mxfile>",
        })
        resp = client.get("/artifacts/documents")
        assert resp.status_code == 200
        docs = resp.get_json()["documents"]
        assert [d["filename"] for d in docs] == ["Vendor_Onboarding.docx"]
        assert docs[0]["size_bytes"] == len(b"fake docx")

    def test_list_documents_is_empty_list_not_error_when_none_exist(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        resp = client.get("/artifacts/documents")
        assert resp.status_code == 200
        assert resp.get_json()["documents"] == []

    def test_download_document_returns_the_real_bytes_as_an_attachment(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"Vendor_Onboarding.docx": b"fake docx bytes"})
        resp = client.get("/artifacts/documents/Vendor_Onboarding.docx/download")
        assert resp.status_code == 200
        assert resp.data == b"fake docx bytes"
        assert "Vendor_Onboarding.docx" in resp.headers.get("Content-Disposition", "")

    def test_download_document_404s_for_an_unknown_filename(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        resp = client.get("/artifacts/documents/Nonexistent.docx/download")
        assert resp.status_code == 404

    def test_download_document_rejects_a_path_traversal_attempt(self, monkeypatch, tmp_path):
        # A secret file OUTSIDE output/ (a sibling of it) must never be
        # reachable through this route, regardless of how the traversal
        # is encoded in the URL.
        secret = tmp_path / "secret.txt"
        secret.write_text("do not leak me", encoding="utf-8")
        client = self._build_client(monkeypatch, tmp_path, {"real.docx": b"ok"})
        resp = client.get("/artifacts/documents/..%2Fsecret.txt/download")
        assert resp.status_code == 404

    def test_download_document_rejects_a_non_docx_file_even_if_present_in_output(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"process_data.json": "{}"})
        resp = client.get("/artifacts/documents/process_data.json/download")
        assert resp.status_code == 404

    def test_download_cloudarch_returns_the_real_xml_bytes(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"cloudarch_drawio.xml": "<mxfile>hi</mxfile>"})
        resp = client.get("/artifacts/cloudarch/download")
        assert resp.status_code == 200
        assert resp.data == b"<mxfile>hi</mxfile>"
        assert "cloudarch_drawio.xml" in resp.headers.get("Content-Disposition", "")

    def test_download_cloudarch_404s_when_not_yet_generated(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path)
        resp = client.get("/artifacts/cloudarch/download")
        assert resp.status_code == 404

    def test_downloads_require_auth_when_configured(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WEBAPIKEY", "secret")
        client = self._build_client(monkeypatch, tmp_path, {
            "Vendor_Onboarding.docx": b"ok", "cloudarch_drawio.xml": "<mxfile></mxfile>",
        })
        assert client.get("/artifacts/documents").status_code == 401
        assert client.get("/artifacts/documents/Vendor_Onboarding.docx/download").status_code == 401
        assert client.get("/artifacts/cloudarch/download").status_code == 401

    def test_list_and_download_resolve_a_session_scoped_document_via_query_param(self, monkeypatch, tmp_path):
        # Regression test -- see TestArtifactRoute's identically-named test
        # for the full rationale (the web client passes session_id as a
        # query param, not via the cookie, on every GET /artifacts/* call).
        client = self._build_client(monkeypatch, tmp_path)
        with paths.use_session("doc-session"):
            session_output_dir = os.path.join(paths.OUTPUT_DIR, "doc-session")
            os.makedirs(session_output_dir, exist_ok=True)
            with open(os.path.join(session_output_dir, "Vendor_Onboarding.docx"), "wb") as f:
                f.write(b"session-scoped docx bytes")

        assert client.get("/artifacts/documents").get_json()["documents"] == []

        listed = client.get("/artifacts/documents?session_id=doc-session").get_json()["documents"]
        assert [d["filename"] for d in listed] == ["Vendor_Onboarding.docx"]

        assert client.get("/artifacts/documents/Vendor_Onboarding.docx/download").status_code == 404

        resp = client.get("/artifacts/documents/Vendor_Onboarding.docx/download?session_id=doc-session")
        assert resp.status_code == 200
        assert resp.data == b"session-scoped docx bytes"


class TestAgentInstructionsRoute:
    """GET /agents/<name>/instructions -- read-only lookup of an agent's
    real HOCON "instructions" text, for the web client's Agent Network tab
    hover feature. _PROJECT_ROOT is monkeypatched to an isolated tmp_path,
    same as TestArtifactRoute above -- and the module-level instructions
    index cache is explicitly reset before each test, since it's built
    ONCE per process and would otherwise still hold whichever OTHER
    test's tmp_path registries happened to populate it first."""

    _SAMPLE_NETWORK = """
    {
        "tools": [
            {
                "name": "Front_Man",
                "function": {"description": "Entry point."},
                "instructions": "You are the front man.",
                "tools": [
                    {
                        "name": "Nested_Agent",
                        "function": {"description": "A nested helper."},
                        "instructions": "You are the nested helper."
                    },
                    "coded_tool_name"
                ]
            }
        ]
    }
    """

    def _build_client(self, monkeypatch, tmp_path, hocon_files=None):
        monkeypatch.setattr(cli, "_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setattr(cli, "_agent_instructions_index", None)
        registries_dir = tmp_path / "registries"
        registries_dir.mkdir()
        for rel_name, content in (hocon_files or {}).items():
            path = registries_dir / rel_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        app = cli.build_web_app("process_architect", https=False)
        return app.test_client()

    def test_returns_instructions_and_description_for_a_top_level_agent(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"sample.hocon": self._SAMPLE_NETWORK})
        resp = client.get("/agents/Front_Man/instructions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert body["name"] == "Front_Man"
        assert body["instructions"] == "You are the front man."
        assert body["description"] == "Entry point."
        assert body["source_file"] == os.path.join("registries", "sample.hocon")

    def test_returns_instructions_for_an_agent_nested_in_another_agents_own_tools_list(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"sample.hocon": self._SAMPLE_NETWORK})
        resp = client.get("/agents/Nested_Agent/instructions")
        assert resp.status_code == 200
        assert resp.get_json()["instructions"] == "You are the nested helper."

    def test_404_for_an_unknown_agent_name(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"sample.hocon": self._SAMPLE_NETWORK})
        resp = client.get("/agents/Nonexistent_Agent/instructions")
        assert resp.status_code == 404
        assert resp.get_json()["status"] == "error"

    def test_404_for_a_bare_string_entry_a_coded_tool_or_external_agent_reference(self, monkeypatch, tmp_path):
        # "coded_tool_name" appears in the sample network's own tools list,
        # but as a bare string (a coded tool/external-agent reference, not
        # an agent definition with its own "instructions") -- must not be
        # indexed as if it were a real agent.
        client = self._build_client(monkeypatch, tmp_path, {"sample.hocon": self._SAMPLE_NETWORK})
        resp = client.get("/agents/coded_tool_name/instructions")
        assert resp.status_code == 404

    def test_non_network_fragment_files_are_skipped_without_breaking_the_scan(self, monkeypatch, tmp_path):
        # Neither of these parses as a real agent network -- confirms the
        # scan skips them (by filename prefix) rather than choking.
        client = self._build_client(monkeypatch, tmp_path, {
            "sample.hocon": self._SAMPLE_NETWORK,
            "aaosa.hocon": '{"aaosa_instructions": "..."}',
            "manifest.hocon": '{"registries/sample.hocon": true}',
        })
        resp = client.get("/agents/Front_Man/instructions")
        assert resp.status_code == 200

    def test_index_is_built_once_and_reused_across_requests(self, monkeypatch, tmp_path):
        client = self._build_client(monkeypatch, tmp_path, {"sample.hocon": self._SAMPLE_NETWORK})
        client.get("/agents/Front_Man/instructions")
        built_index = cli._agent_instructions_index
        assert built_index is not None
        client.get("/agents/Front_Man/instructions")
        assert cli._agent_instructions_index is built_index  # same object -- not rebuilt

    def test_requires_auth_when_configured(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WEBAPIKEY", "secret")
        client = self._build_client(monkeypatch, tmp_path, {"sample.hocon": self._SAMPLE_NETWORK})
        resp = client.get("/agents/Front_Man/instructions")
        assert resp.status_code == 401

    def test_double_underscore_file_alias_resolves_to_the_files_own_front_man(self, monkeypatch, tmp_path):
        # neuro-san's own naming for a same-server external agent reference
        # (e.g. process_architect.hocon's "/sample") -- ExternalAgentParsing.
        # get_safe_agent_name prepends "__" to the reference path, so a
        # network/graph node for a CROSS-NETWORK call carries this name, not
        # the real front-man name the plain index is keyed by. Confirmed
        # directly against a real hover-over-node 404 in the web client.
        client = self._build_client(monkeypatch, tmp_path, {"sample.hocon": self._SAMPLE_NETWORK})
        resp = client.get("/agents/__sample/instructions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["name"] == "__sample"
        assert body["instructions"] == "You are the front man."
        assert body["source_file"] == os.path.join("registries", "sample.hocon")

    def test_double_underscore_alias_is_skipped_for_a_file_with_no_real_front_man(self, monkeypatch, tmp_path):
        # A file with no agent carrying both "name" and "instructions" (e.g.
        # only non-network fragment-style content) has no front-man to alias
        # at all -- must not raise, just leave that file's "__" alias absent.
        client = self._build_client(monkeypatch, tmp_path, {
            "sample.hocon": self._SAMPLE_NETWORK,
            "empty.hocon": '{"tools": []}',
        })
        resp = client.get("/agents/__empty/instructions")
        assert resp.status_code == 404


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
        # The eviction sweep calls ChatSession.close() directly (not
        # session.session.close()) -- it's the one place responsible for
        # releasing BOTH the attachment-staging directory and the
        # underlying neuro-san session, so this fake mirrors that single
        # entry point rather than the neuro-san session's own close().
        close_calls = []
        return SimpleNamespace(
            last_accessed=last_accessed,
            close=lambda: close_calls.append(True),
            _close_calls=close_calls,
        )

    def _reset(self, monkeypatch):
        # time.monotonic()'s own baseline is platform-dependent -- on a
        # long-uptime dev machine it's already huge, but on a freshly
        # booted CI container it can be well under
        # _WEB_SESSION_SWEEP_INTERVAL_SECONDS (300) itself. A hardcoded
        # 0.0 here relies on "now - 0.0 >= 300" always being true, which
        # is false whenever time.monotonic() < 300 at test time --
        # confirmed directly against a real CI run, where it was ~50 --
        # silently skipping the sweep and making eviction look broken.
        # Anchoring relative to the current clock instead makes "last
        # swept long enough ago to sweep again" true unconditionally.
        monkeypatch.setattr(
            cli, "_web_sessions_last_swept",
            time.monotonic() - cli._WEB_SESSION_SWEEP_INTERVAL_SECONDS - 10,
        )
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


class TestReleaseAnyLeftoverPipelineLock:
    """_release_any_leftover_pipeline_lock -- regression coverage for a
    review finding: POST /chat/<session_id>/stop cancels whatever tool/
    model call is currently in flight via cancel_current_tasks(), but
    there is no guarantee the specific CodedTool call that would have
    released the pipeline lock (doc_generation_tool.py / loop_control_
    tool.py) ever runs afterward. Without this safety net, a cancelled
    turn would leave both the lock AND its background heartbeat
    (process_toolkit.run_lock) running forever -- worse than before that
    heartbeat existed, since it would keep the lock's started_at fresh
    indefinitely, permanently defeating the staleness-based self-healing
    every pipeline run still depends on for a genuine crash/abandonment.
    """

    def test_no_sly_data_is_a_safe_noop(self):
        cli._release_any_leftover_pipeline_lock(None)  # must not raise

    def test_no_token_in_sly_data_is_a_safe_noop(self):
        cli._release_any_leftover_pipeline_lock({})  # must not raise

    def test_leftover_token_is_released_and_its_heartbeat_stopped(self):
        from process_toolkit.run_lock import acquire_pipeline_lock, start_pipeline_lock_heartbeat, _heartbeats

        token = acquire_pipeline_lock("a neuro-san pipeline")
        start_pipeline_lock_heartbeat("a neuro-san pipeline", token)
        assert token in _heartbeats

        cli._release_any_leftover_pipeline_lock({cli.PIPELINE_LOCK_TOKEN_KEY: token})

        assert token not in _heartbeats
        acquire_pipeline_lock("a different pipeline")  # must not raise -- released above


class TestSendStreamingCancellationReleasesLeftoverLock:
    """send_streaming's own cancellation path must still release a
    leftover pipeline lock -- see TestReleaseAnyLeftoverPipelineLock's
    own docstring for why this specific path is the one that matters."""

    def test_cancellation_releases_a_leftover_pipeline_lock(self):
        from process_toolkit.run_lock import acquire_pipeline_lock, _heartbeats, start_pipeline_lock_heartbeat

        class _CancelledStreamingSession:
            def streaming_chat(self, chat_request):
                yield {"response": {"type": "progress", "origin": [], "text": "starting"}}
                raise asyncio.CancelledError()

        token = acquire_pipeline_lock("a neuro-san pipeline")
        start_pipeline_lock_heartbeat("a neuro-san pipeline", token)

        session = cli.ChatSession.__new__(cli.ChatSession)
        session.sly_data = {cli.PIPELINE_LOCK_TOKEN_KEY: token}
        session.chat_context = None
        session._lock = threading.Lock()
        session.session = _CancelledStreamingSession()
        session.input_processor = _StubStreamingInputProcessor()

        events = list(session.send_streaming("hello"))

        assert events[-1]["status"] == "stopped"
        assert token not in _heartbeats
        acquire_pipeline_lock("a different pipeline")  # must not raise -- released above
