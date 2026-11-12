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

import logging

from coded_tools.common.logging_setup import _quiet_known_noisy_third_party_loggers, _resolve_log_level


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


class TestQuietKnownNoisyThirdPartyLoggers:
    """Regression coverage for a real production bug: neuro_san's own
    RunContextRunnable logs every model-call retry attempt and the full
    exception traceback against a bare logging.getLogger("RunContextRunnable")
    with no handler of its own -- Python's logging.lastResort then dumped
    all of it to stderr, burying this project's own clean
    "[ArchitectBot]: ..." reply under noise, most visibly (and
    repeatedly, turn after turn) on an LLM-provider billing failure."""

    def _reset(self, name: str) -> logging.Logger:
        third_party_logger = logging.getLogger(name)
        for handler in list(third_party_logger.handlers):
            third_party_logger.removeHandler(handler)
        third_party_logger.propagate = True
        return third_party_logger

    def test_attaches_the_given_handler_and_stops_propagation(self):
        third_party_logger = self._reset("RunContextRunnable")
        handler = logging.NullHandler()

        _quiet_known_noisy_third_party_loggers(handler)

        assert handler in third_party_logger.handlers
        assert third_party_logger.propagate is False

    def test_is_idempotent_once_a_handler_is_already_attached(self):
        third_party_logger = self._reset("RunContextRunnable")
        first_handler = logging.NullHandler()
        _quiet_known_noisy_third_party_loggers(first_handler)

        second_handler = logging.NullHandler()
        _quiet_known_noisy_third_party_loggers(second_handler)

        assert third_party_logger.handlers == [first_handler]
