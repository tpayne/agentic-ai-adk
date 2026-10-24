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

    return logger
