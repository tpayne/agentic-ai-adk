"""Unit tests for cli.py's own control-flow logic (argument parsing, control
lines, shell-escape detection) -- the parts that don't require a live LLM
credential to exercise. ChatSession itself (the part that actually talks to
neuro-san) is exercised manually/at the integration level elsewhere in this
project (ns chat), the same way every other network's LLM-backed behavior
is -- there's no API key in this environment to drive a real turn through
it in a unit test.
"""

import asyncio

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
                "token_accounting": {"gemini-3-flash": {"total_tokens": 42}},
            }

    session.input_processor = _StubInputProcessor()
    with caplog.at_level("INFO", logger="ProcessArchitect.CLI.Trace"):
        result = session.send("hi")
    assert result == "done"
    assert any("total_tokens" in r.getMessage() for r in caplog.records)
