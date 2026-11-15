import pytest

from process_interface import config


class TestResolve:
    def test_defaults_to_local_with_no_env_vars_set(self):
        resolved = config.resolve()
        assert resolved.mode == "local"
        assert resolved.mcp_url is None

    def test_mode_mcp_is_case_and_whitespace_insensitive(self, monkeypatch):
        for value in ("mcp", "MCP", " Mcp ", "McP"):
            monkeypatch.setenv("PROCESS_TOOLKIT_MODE", value)
            monkeypatch.setenv("PROCESS_TOOLKIT_MCP_URL", "http://localhost:8765/mcp")
            assert config.resolve().mode == "mcp"

    @pytest.mark.parametrize("value", ["local", "", "mcpx", "remote"])
    def test_anything_unrecognized_fails_safe_to_local(self, monkeypatch, value):
        # No PROCESS_TOOLKIT_MCP_URL is set here on purpose -- if any of
        # these values were misclassified as "mcp", resolve() would raise
        # ProcessInterfaceConfigError instead of returning cleanly, so this
        # test also doubles as proof none of them are.
        monkeypatch.setenv("PROCESS_TOOLKIT_MODE", value)
        assert config.resolve().mode == "local"

    def test_mcp_mode_without_a_url_raises_a_clear_config_error(self, monkeypatch):
        monkeypatch.setenv("PROCESS_TOOLKIT_MODE", "mcp")
        with pytest.raises(config.ProcessInterfaceConfigError, match="PROCESS_TOOLKIT_MCP_URL"):
            config.resolve()

    def test_mcp_mode_with_a_url_resolves_cleanly(self, monkeypatch):
        monkeypatch.setenv("PROCESS_TOOLKIT_MODE", "mcp")
        monkeypatch.setenv("PROCESS_TOOLKIT_MCP_URL", "http://127.0.0.1:8765/mcp")
        resolved = config.resolve()
        assert resolved.mode == "mcp"
        assert resolved.mcp_url == "http://127.0.0.1:8765/mcp"

    def test_timeout_defaults_and_falls_back_on_garbage_input(self, monkeypatch):
        assert config.resolve().mcp_timeout == config.DEFAULT_MCP_TIMEOUT_SECONDS
        monkeypatch.setenv("PROCESS_TOOLKIT_MCP_TIMEOUT", "not-a-number")
        assert config.resolve().mcp_timeout == config.DEFAULT_MCP_TIMEOUT_SECONDS
        monkeypatch.setenv("PROCESS_TOOLKIT_MCP_TIMEOUT", "5.5")
        assert config.resolve().mcp_timeout == 5.5


class TestIsMcpMode:
    def test_matches_resolve(self, monkeypatch):
        assert config.is_mcp_mode() is False
        monkeypatch.setenv("PROCESS_TOOLKIT_MODE", "mcp")
        monkeypatch.setenv("PROCESS_TOOLKIT_MCP_URL", "http://127.0.0.1:8765/mcp")
        assert config.is_mcp_mode() is True
