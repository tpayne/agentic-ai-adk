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
