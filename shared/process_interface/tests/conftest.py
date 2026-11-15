import pytest

from process_toolkit import paths


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """Mirrors process_toolkit's own tests/conftest.py fixture -- every
    test gets its own throwaway output directory."""
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture(autouse=True)
def reset_mcp_env(monkeypatch):
    """Every test starts with a clean PROCESS_TOOLKIT_MODE/_MCP_URL --
    config.resolve() reads fresh from os.environ, so without this a test
    could leak its mode/URL into the next one."""
    monkeypatch.delenv("PROCESS_TOOLKIT_MODE", raising=False)
    monkeypatch.delenv("PROCESS_TOOLKIT_MCP_URL", raising=False)
    monkeypatch.delenv("PROCESS_TOOLKIT_MCP_TIMEOUT", raising=False)
    yield
