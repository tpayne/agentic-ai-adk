"""Unit tests for server.py's internal helpers, called directly as plain
Python functions -- never through an MCP client/transport (that full-stack
coverage, including these same helpers wired into real tools, lives in
test_server.py).
"""

import base64
import os
import sys
from types import SimpleNamespace

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import server


class TestRateLimitClientId:
    """_rate_limit_client_id delegates to fastmcp's own get_http_request(),
    which raises RuntimeError outside a real HTTP request (stdio, this
    project's in-memory test transport) rather than returning None --
    exercised here by monkeypatching server.get_http_request directly,
    since actually driving a real HTTP request just to test this one
    branch would be the tail wagging the dog."""

    def test_uses_the_connecting_ips_host_when_a_real_http_request_is_active(self, monkeypatch):
        fake_request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.5"))
        monkeypatch.setattr(server, "get_http_request", lambda: fake_request)
        assert server._rate_limit_client_id(context=None) == "203.0.113.5"

    def test_falls_back_when_there_is_no_active_http_request(self, monkeypatch):
        def _raise():
            raise RuntimeError("No active HTTP request found.")

        monkeypatch.setattr(server, "get_http_request", _raise)
        assert server._rate_limit_client_id(context=None) == "non-http-client"

    def test_falls_back_when_the_request_has_no_client_info(self, monkeypatch):
        fake_request = SimpleNamespace(client=None)
        monkeypatch.setattr(server, "get_http_request", lambda: fake_request)
        assert server._rate_limit_client_id(context=None) == "non-http-client"


class TestRateLimitingEnabledToggle:
    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "anything-else"])
    def test_truthy_values_enable_it(self, monkeypatch, value):
        monkeypatch.setenv("PROCESS_TOOLKIT_MCP_RATE_LIMIT_ENABLED", value)
        assert server._rate_limiting_enabled() is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "off", "  off  "])
    def test_falsy_values_disable_it(self, monkeypatch, value):
        monkeypatch.setenv("PROCESS_TOOLKIT_MCP_RATE_LIMIT_ENABLED", value)
        assert server._rate_limiting_enabled() is False

    def test_defaults_to_enabled_when_unset(self, monkeypatch):
        monkeypatch.delenv("PROCESS_TOOLKIT_MCP_RATE_LIMIT_ENABLED", raising=False)
        assert server._rate_limiting_enabled() is True


class TestToolCallRateLimitingMiddleware:
    """Proves the actual enforcement logic -- token-bucket limiting scoped
    to tools/call only -- against a short-lived, dedicated FastMCP
    instance built fresh in each test, never the shared server.mcp
    singleton (see conftest.py for why that one has rate limiting
    disabled for the whole test session)."""

    def _make_app(self, **middleware_kwargs):
        app = FastMCP("rate-limit-test")
        app.add_middleware(server.ToolCallRateLimitingMiddleware(
            get_client_id=lambda context: "fixed-test-client",
            **middleware_kwargs,
        ))

        @app.tool
        def echo(text: str) -> str:
            return text

        return app

    async def test_admits_calls_up_to_the_burst_capacity(self):
        app = self._make_app(max_requests_per_second=1.0, burst_capacity=2)
        async with Client(app) as client:
            await client.call_tool("echo", {"text": "a"})
            await client.call_tool("echo", {"text": "b"})

    async def test_rejects_once_the_burst_capacity_is_exhausted(self):
        app = self._make_app(max_requests_per_second=1.0, burst_capacity=1)
        async with Client(app) as client:
            await client.call_tool("echo", {"text": "a"})
            with pytest.raises(Exception, match="Rate limit exceeded"):
                await client.call_tool("echo", {"text": "b"})

    async def test_only_tool_calls_are_throttled_not_list_tools_or_initialize(self):
        # on_call_tool is the only hook this class implements -- on_request
        # (which the base Middleware.on_request no-ops) is what fires for
        # every other message type, so exhausting the tool-call bucket
        # must never affect list_tools, no matter how many times it's
        # called in the same session.
        app = self._make_app(max_requests_per_second=1.0, burst_capacity=1)
        async with Client(app) as client:
            await client.call_tool("echo", {"text": "a"})
            with pytest.raises(Exception, match="Rate limit exceeded"):
                await client.call_tool("echo", {"text": "b"})
            for _ in range(10):
                await client.list_tools()


class TestDomainOrError:
    def test_returns_the_matching_domain_ops(self):
        ops = server._domain_or_error("togaf")
        assert ops is server.dispatch.DOMAINS["togaf"]

    def test_raises_a_tool_error_naming_the_valid_schema_types(self):
        with pytest.raises(ToolError, match="Unknown schema_type 'bogus'"):
            server._domain_or_error("bogus")


class TestSession:
    def test_none_session_id_is_a_no_op_context_manager(self):
        with server._session(None):
            pass  # must not raise

    def test_a_safe_session_id_is_accepted(self):
        with server._session("my-session_1"):
            pass  # must not raise

    def test_an_unsafe_session_id_raises_a_tool_error_not_a_raw_value_error(self):
        with pytest.raises(ToolError):
            with server._session("../escape"):
                pass


class TestSnapshotAndDiffMtimes:
    def test_snapshot_only_includes_files_matching_the_suffix(self, tmp_path):
        (tmp_path / "a.docx").write_text("x")
        (tmp_path / "b.png").write_text("x")
        snapshot = server._snapshot_mtimes(str(tmp_path), ".docx")
        assert set(snapshot) == {"a.docx"}

    def test_snapshot_of_a_missing_directory_is_empty(self, tmp_path):
        assert server._snapshot_mtimes(str(tmp_path / "nope"), ".docx") == {}

    def test_new_or_changed_detects_a_brand_new_file(self, tmp_path):
        before = server._snapshot_mtimes(str(tmp_path), ".docx")
        (tmp_path / "new.docx").write_text("x")
        changed = server._new_or_changed(before, str(tmp_path), ".docx")
        assert changed == ["new.docx"]

    def test_new_or_changed_detects_a_modified_file_via_mtime(self, tmp_path):
        path = tmp_path / "existing.docx"
        path.write_text("x")
        before = server._snapshot_mtimes(str(tmp_path), ".docx")
        os.utime(path, (before["existing.docx"] + 10, before["existing.docx"] + 10))
        changed = server._new_or_changed(before, str(tmp_path), ".docx")
        assert changed == ["existing.docx"]

    def test_new_or_changed_ignores_untouched_files(self, tmp_path):
        (tmp_path / "untouched.docx").write_text("x")
        before = server._snapshot_mtimes(str(tmp_path), ".docx")
        assert server._new_or_changed(before, str(tmp_path), ".docx") == []


class TestEncodeFile:
    def test_round_trips_real_bytes_through_base64(self, tmp_path):
        path = tmp_path / "artifact.bin"
        path.write_bytes(b"\x00\x01real bytes\xff")
        encoded = server._encode_file(str(path))
        assert encoded["filename"] == "artifact.bin"
        assert encoded["size_bytes"] == len(b"\x00\x01real bytes\xff")
        assert base64.b64decode(encoded["base64"]) == b"\x00\x01real bytes\xff"


class TestParseArgsSsl:
    """_parse_args' SSL validation, exercised via real argv/argparse (not
    by calling some inner helper directly) -- argparse.error() calls
    sys.exit(2) after printing usage, so that's the observable contract a
    caller running `python server.py --bad-combination` actually sees."""

    def test_both_certfile_and_keyfile_together_is_accepted(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "argv", [
            "server.py", "--ssl-certfile", str(tmp_path / "c.pem"), "--ssl-keyfile", str(tmp_path / "k.pem"),
        ])
        args = server._parse_args()
        assert args.ssl_certfile == str(tmp_path / "c.pem")
        assert args.ssl_keyfile == str(tmp_path / "k.pem")

    def test_certfile_without_keyfile_exits_with_an_error(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sys, "argv", ["server.py", "--ssl-certfile", str(tmp_path / "c.pem")])
        with pytest.raises(SystemExit):
            server._parse_args()
        assert "must be given together" in capsys.readouterr().err

    def test_keyfile_without_certfile_exits_with_an_error(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sys, "argv", ["server.py", "--ssl-keyfile", str(tmp_path / "k.pem")])
        with pytest.raises(SystemExit):
            server._parse_args()
        assert "must be given together" in capsys.readouterr().err

    def test_ssl_args_combined_with_stdio_transport_exits_with_an_error(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sys, "argv", [
            "server.py", "--transport", "stdio",
            "--ssl-certfile", str(tmp_path / "c.pem"), "--ssl-keyfile", str(tmp_path / "k.pem"),
        ])
        with pytest.raises(SystemExit):
            server._parse_args()
        assert "only apply to --transport http" in capsys.readouterr().err

    def test_neither_flag_is_fine_and_defaults_to_none(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["server.py"])
        args = server._parse_args()
        assert args.ssl_certfile is None
        assert args.ssl_keyfile is None


class TestUvicornSslConfig:
    def test_empty_dict_when_no_certfile_is_configured(self):
        args = SimpleNamespace(ssl_certfile=None, ssl_keyfile=None)
        assert server._uvicorn_ssl_config(args) == {}

    def test_includes_certfile_and_keyfile_when_configured(self, monkeypatch):
        monkeypatch.delenv("PROCESS_TOOLKIT_MCP_SSL_KEYFILE_PASSWORD", raising=False)
        args = SimpleNamespace(ssl_certfile="/tmp/c.pem", ssl_keyfile="/tmp/k.pem")
        assert server._uvicorn_ssl_config(args) == {
            "ssl_certfile": "/tmp/c.pem", "ssl_keyfile": "/tmp/k.pem",
        }

    def test_includes_the_keyfile_password_when_set_via_env(self, monkeypatch):
        monkeypatch.setenv("PROCESS_TOOLKIT_MCP_SSL_KEYFILE_PASSWORD", "secret")
        args = SimpleNamespace(ssl_certfile="/tmp/c.pem", ssl_keyfile="/tmp/k.pem")
        assert server._uvicorn_ssl_config(args) == {
            "ssl_certfile": "/tmp/c.pem", "ssl_keyfile": "/tmp/k.pem", "ssl_keyfile_password": "secret",
        }


class TestSafeArtifactPath:
    def test_resolves_a_real_file_in_the_current_session_output_dir(self, tmp_path):
        (tmp_path / "report.docx").write_text("x")
        resolved = server._safe_artifact_path("report.docx")
        assert resolved == str(tmp_path / "report.docx")

    def test_rejects_a_path_traversal_attempt(self, tmp_path):
        secret_dir = tmp_path.parent / "secret_sibling"
        secret_dir.mkdir(exist_ok=True)
        (secret_dir / "secret.txt").write_text("do not leak me")
        with pytest.raises(ToolError, match="No such artifact"):
            server._safe_artifact_path("../secret_sibling/secret.txt")

    def test_rejects_an_empty_filename(self, tmp_path):
        with pytest.raises(ToolError, match="No such artifact"):
            server._safe_artifact_path("")

    def test_rejects_a_filename_that_does_not_exist(self, tmp_path):
        with pytest.raises(ToolError, match="No such artifact"):
            server._safe_artifact_path("nope.docx")
