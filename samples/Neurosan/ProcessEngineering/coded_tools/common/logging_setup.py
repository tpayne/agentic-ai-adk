"""Central logging configuration, matching the ADK original's own
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
import os
import sys

_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def configure_logging(project_root: str, log_filename: str) -> logging.Logger:
    logger = logging.getLogger("ProcessArchitect")
    if logger.handlers:
        return logger

    log_dir = os.path.join(project_root, "output", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, log_filename)

    log_format = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(log_format)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.WARNING)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    log_level = os.environ.get("LOGLEVEL", "WARNING").upper()
    if log_level not in _VALID_LOG_LEVELS:
        log_level = "WARNING"
    logger.setLevel(log_level)

    return logger
