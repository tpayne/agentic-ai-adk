"""Tests _transport.py against a real, locally-started Streamable HTTP
server (a tiny throwaway FastMCP app, not the full ProcessToolkitServer --
that server's own tool catalog is exercised through process_interface's
switchable modules in later phases, not here). This proves the background-
loop/persistent-Client bridge actually works end-to-end over a real socket,
not just in-process."""

import socket
import threading
import time

import pytest
from fastmcp import FastMCP

from process_interface import _transport, config


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_server(monkeypatch):
    app = FastMCP("transport-test")

    @app.tool
    def echo(text: str) -> dict:
        return {"echo": text}

    port = _free_port()
    thread = threading.Thread(
        target=lambda: app.run(transport="http", host="127.0.0.1", port=port, show_banner=False),
        daemon=True,
    )
    thread.start()

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("test server did not start listening in time")

    url = f"http://127.0.0.1:{port}/mcp"
    monkeypatch.setenv("PROCESS_TOOLKIT_MODE", "mcp")
    monkeypatch.setenv("PROCESS_TOOLKIT_MCP_URL", url)
    yield url
    _transport.reset()


class TestCall:
    def test_calls_a_real_tool_over_real_http_and_returns_its_data(self, running_server):
        result = _transport.call("echo", {"text": "hello"})
        assert result == {"echo": "hello"}

    def test_reuses_the_connection_across_multiple_calls(self, running_server):
        _transport.call("echo", {"text": "a"})
        client_after_first = _transport._client
        _transport.call("echo", {"text": "b"})
        assert _transport._client is client_after_first

    def test_recovers_after_reset_forces_a_reconnect(self, running_server):
        _transport.call("echo", {"text": "a"})
        _transport.reset()
        assert _transport._client is None
        result = _transport.call("echo", {"text": "b"})
        assert result == {"echo": "b"}

    def test_raises_a_clear_config_error_when_no_url_is_set(self, monkeypatch):
        monkeypatch.delenv("PROCESS_TOOLKIT_MCP_URL", raising=False)
        monkeypatch.setenv("PROCESS_TOOLKIT_MODE", "mcp")
        # mode=mcp with no URL already raises at config.resolve() -- confirm
        # _transport.call surfaces the same clear error rather than a raw
        # connection failure.
        with pytest.raises(config.ProcessInterfaceConfigError):
            _transport.call("echo", {"text": "a"})
