"""Central logging configuration, matching the ADK port's own
process_agents/common/agent.py setup exactly: a dedicated "ProcessArchitect"
logger (not the root logger -- this scopes capture to this project's own
ProcessArchitect.* child loggers, not every third-party library's noise)
with its own file + console handlers and propagate=False, a LOGLEVEL env
var controlling the file handler, and a console handler fixed at WARNING+
regardless of LOGLEVEL so a DEBUG-level file trace never floods an
interactive terminal.

Call configure_logging() from any entry point that should produce a log
file. It's idempotent (checks for existing handlers on the "ProcessArchitect"
logger) so it's safe to call from multiple entry points -- whichever runs
first wins, and later calls (e.g. a coded_tools/__init__.py import that
happens to run after cli.py has already configured things) are no-ops.
"""

import logging
import logging.handlers
import os
import sys

_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# A long-running web service (run_web_service/-d --flask) never restarts
# on its own to truncate this file the way a one-shot CLI invocation
# implicitly does -- a plain FileHandler grew it unbounded for the life
# of the process. 10MB x 5 backups (50MB ceiling) is generous for this
# project's own request volume while still being a real, enforced bound.
_LOG_MAX_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5

# Third-party loggers that, left unconfigured, fall straight through to
# Python's own logging.lastResort handler (a bare StreamHandler on stderr
# at WARNING+, used whenever a logger has no handler anywhere in its own
# propagation chain, root included) -- the "ProcessArchitect" logger
# above deliberately does NOT touch the root logger (see this module's
# own docstring), so none of this was ever being swallowed by it either;
# it simply had nowhere else to go. CONFIRMED AS A REAL PRODUCTION BUG:
# neuro_san's own RunContextRunnable (internals/run_context/langchain/
# core/run_context_runnable.py) logs every retry attempt via
# `self.sensitive_logger.warning(...)` and the full exception traceback
# via `.error(...)` against a bare `logging.getLogger("RunContextRunnable")`
# -- with no handler of its own, every one of those (three retries plus a
# full traceback, per failed model call) landed on stderr via lastResort,
# burying this project's own clean "[ArchitectBot]: ..." reply (see
# cli.py's own _friendly_llm_failure_message) under noise a user has no
# reason to read live -- genuinely useful for after-the-fact debugging,
# just not on the interactive console. Most visible on an LLM-provider
# billing failure (depleted prepaid credits), where every SUBSEQUENT turn
# repeats the same multi-retry dump, since that failure is permanent
# until the user tops up credits -- retrying never helps, so nothing
# about the repeated dump is actionable information worth seeing twice.
_NOISY_THIRD_PARTY_LOGGER_NAMES = ("RunContextRunnable",)


def _quiet_known_noisy_third_party_loggers(file_handler: logging.Handler) -> None:
    """Routes each of _NOISY_THIRD_PARTY_LOGGER_NAMES into the SAME log
    file this project's own "ProcessArchitect" logger already writes to
    (reusing the same handler instance -- Python's logging module
    supports one Handler being attached to multiple Loggers) and cuts
    propagation, so records land only in the file, never on the console
    via lastResort. A no-op for any logger that already has a handler of
    its own (idempotent, matching configure_logging's own guard) --
    something else already configured it, so this leaves that alone."""
    for name in _NOISY_THIRD_PARTY_LOGGER_NAMES:
        third_party_logger = logging.getLogger(name)
        if third_party_logger.handlers:
            continue
        third_party_logger.addHandler(file_handler)
        third_party_logger.propagate = False


def _resolve_log_level() -> str:
    """Reads LOGLEVEL from the environment, falling back to INFO -- not
    WARNING -- when it's unset or not one of the five recognized values.

    The ADK port ships its own equivalent default as DEBUG in
    properties/agentapp.properties (that code's own WARNING fallback only
    applies if that file is ever missing/misread), so its turn-completion/
    outcome logs are visible out of the box. This project has no
    equivalent checked-in default-setting file -- an unset LOGLEVEL used
    to mean every ProcessArchitect.* INFO call (turn completion/duration/
    usage, idle-session eviction notices) was silently suppressed even
    though nothing explicitly asked for that, leaving a production
    deployment with zero after-the-fact trace for anything short of an
    exception. The console handler in configure_logging stays fixed at
    WARNING+ regardless of this, so raising the default only affects the
    file -- the per-message agent/tool trace still logs at DEBUG and
    stays opt-in.

    :return: One of _VALID_LOG_LEVELS.
    """
    log_level = os.environ.get("LOGLEVEL", "INFO").upper()
    return log_level if log_level in _VALID_LOG_LEVELS else "INFO"


def configure_logging(project_root: str, log_filename: str) -> logging.Logger:
    logger = logging.getLogger("ProcessArchitect")
    if logger.handlers:
        return logger

    log_dir = os.path.join(project_root, "output", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, log_filename)

    log_format = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=_LOG_MAX_BYTES, backupCount=_LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(log_format)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.WARNING)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    logger.setLevel(_resolve_log_level())

    _quiet_known_noisy_third_party_loggers(file_handler)

    return logger
