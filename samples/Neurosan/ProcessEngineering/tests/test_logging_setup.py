"""_resolve_log_level's default -- regression coverage for a review
finding: with no checked-in default-setting config file (unlike the ADK
original's properties/agentapp.properties, which ships LOGLEVEL=DEBUG), an
unset LOGLEVEL used to mean every ProcessArchitect.* INFO call (turn
completion/duration/usage, idle-session eviction notices) was silently
suppressed by default.

configure_logging() itself is deliberately NOT exercised end-to-end here:
it's idempotent based on whether the "ProcessArchitect" logger already has
handlers, and that logger is configured for real as a side effect of
importing coded_tools (see this project's own cli.py comment on that), so
by the time any test runs it's already been configured once for the whole
process -- exactly the scenario configure_logging's own docstring says is
expected ("whichever runs first wins"). _resolve_log_level is the pure
piece actually worth pinning down in isolation.
"""

from coded_tools.common.logging_setup import _resolve_log_level


def test_default_is_info_not_warning(monkeypatch):
    monkeypatch.delenv("LOGLEVEL", raising=False)
    assert _resolve_log_level() == "INFO"


def test_loglevel_env_var_is_honored(monkeypatch):
    monkeypatch.setenv("LOGLEVEL", "DEBUG")
    assert _resolve_log_level() == "DEBUG"


def test_loglevel_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LOGLEVEL", "debug")
    assert _resolve_log_level() == "DEBUG"


def test_invalid_loglevel_falls_back_to_info(monkeypatch):
    monkeypatch.setenv("LOGLEVEL", "NOT-A-REAL-LEVEL")
    assert _resolve_log_level() == "INFO"
