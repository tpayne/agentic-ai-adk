import os

from coded_tools.common.logging_setup import configure_logging

# This module is guaranteed to execute before any individual CodedTool
# class loads, regardless of entry point (cli.py, `ns chat`, `ns run`/
# nsflow server) -- Python always runs a package's __init__.py before any
# of its submodules, and every coded tool is imported via a dotted path
# starting with "coded_tools.". That same rule means cli.py's own attempt
# to call configure_logging() itself would always lose this race: merely
# importing anything from coded_tools.common.logging_setup already runs
# THIS file first. So cli.py instead sets PROCESS_ARCHITECT_LOG_FILENAME
# before doing that import, and this is the single place that actually
# calls configure_logging() -- for cli.py that env var is already "cli.log"
# by the time this runs; for the `ns chat`/`ns run` server path (which
# never executes cli.py at all, and previously had no equivalent logging
# setup whatsoever), the env var is unset and this falls back to its own
# default, so the two entry points' logs land in separate files instead of
# interleaving in one.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_FILENAME = os.environ.get("PROCESS_ARCHITECT_LOG_FILENAME", "ns_server.log")
configure_logging(_PROJECT_ROOT, _LOG_FILENAME)
