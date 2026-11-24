import pytest

from process_toolkit import paths


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """Mirrors process_toolkit's own tests/conftest.py fixture -- every
    test gets its own throwaway output directory."""
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture(autouse=True)
def configure_fastmcp_home(tmp_path, monkeypatch):
    """Ensures FastMCP uses a safe, writable directory inside tmp_path rather
    than ~/Library/Application Support/fastmcp which fails in sandboxed environments."""
    fastmcp_dir = tmp_path / "fastmcp_home"
    fastmcp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("FASTMCP_HOME", str(fastmcp_dir))
    yield fastmcp_dir


@pytest.fixture(autouse=True)
def reset_mcp_env(monkeypatch):
    """Every test starts with a clean PROCESS_TOOLKIT_MODE/_MCP_URL --
    config.resolve() reads fresh from os.environ, so without this a test
    could leak its mode/URL into the next one."""
    monkeypatch.delenv("PROCESS_TOOLKIT_MODE", raising=False)
    monkeypatch.delenv("PROCESS_TOOLKIT_MCP_URL", raising=False)
    monkeypatch.delenv("PROCESS_TOOLKIT_MCP_TIMEOUT", raising=False)
    yield
