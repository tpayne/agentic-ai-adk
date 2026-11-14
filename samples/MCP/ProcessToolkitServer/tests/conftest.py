import os

# Must run before anything in this directory does `import server` --
# pytest always loads a directory's conftest.py before collecting/
# importing its test modules, and server.py decides whether to install
# ToolCallRateLimitingMiddleware onto the shared server.mcp singleton at
# IMPORT time (`if _rate_limiting_enabled(): mcp.add_middleware(...)`).
#
# Rate limiting is keyed by connecting IP (see server._rate_limit_client_id),
# which doesn't exist under this project's in-memory fastmcp.Client(server.mcp)
# test transport -- every test in this directory would fall back to the
# SAME constant key, meaning the whole test session would share ONE token
# bucket for its entire lifetime, not one per test. With the production
# default (burst=10, 5/sec), the suite's own tool-call volume would exhaust
# that one shared bucket within the first couple of test functions and
# start failing unrelated tests with "Rate limit exceeded" for the rest of
# the run. Disabling it here keeps the other ~50 tests in this directory
# testing what they're actually about; the rate-limiting feature itself
# (the middleware class, the client-id function, the enabled/disabled
# toggle) is tested directly in tests/test_server_helpers.py against
# short-lived, dedicated FastMCP instances that never touch this shared
# bucket.
os.environ.setdefault("PROCESS_TOOLKIT_MCP_RATE_LIMIT_ENABLED", "false")

import pytest

from process_toolkit import paths


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """Every test gets its own throwaway output directory -- mirrors
    process_toolkit's own tests/conftest.py and both agent apps' identical
    fixture, so this new server's tests never touch a real output/ dir."""
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    yield tmp_path
