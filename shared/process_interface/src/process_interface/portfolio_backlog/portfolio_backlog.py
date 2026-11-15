"""Switchable, with the same local-state-first shape as requirements_summary/
proposal_response/test_specification -- see that module's docstring for the
general reasoning. This domain's own quirk: save_portfolio_backlog does
validate+render in one call (there's no separate persist_final step), so
its MCP-mode branch calls generate_portfolio_backlog (not persist_json) and
materializes the returned workbook to the same local path process_toolkit
would have used, via _artifacts, before returning the server's message.
"""

from typing import Any, Dict, Optional

from process_toolkit.portfolio_backlog.portfolio_backlog import (
    PORTFOLIO_BACKLOG_FILENAME,
    PORTFOLIO_BACKLOG_WORKBOOK_FILENAME,
    STATE_KEY,
    StateLike,
)
from process_toolkit.portfolio_backlog import portfolio_backlog as _toolkit

from process_interface import config, paths, _transport, _artifacts
from process_interface.schema._common import mirror_local_copy

__all__ = [
    "PORTFOLIO_BACKLOG_FILENAME",
    "PORTFOLIO_BACKLOG_WORKBOOK_FILENAME",
    "STATE_KEY",
    "StateLike",
    "save_portfolio_backlog",
    "load_portfolio_backlog",
]


def save_portfolio_backlog(backlog: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(backlog, dict):
        return "ERROR: backlog must be a JSON object."

    if not config.is_mcp_mode():
        return _toolkit.save_portfolio_backlog(backlog, state)

    try:
        result = _transport.call(
            "generate_portfolio_backlog",
            {"backlog": backlog, "session_id": paths.current_session_id()},
        )
        message = result["message"]
        if message.startswith("SUCCESS"):
            _artifacts.materialize_one(result.get("workbook"))
            # The JSON baseline itself isn't returned as a base64 artifact
            # by generate_portfolio_backlog (only the rendered workbook
            # is) -- mirror it locally too, same reasoning as the schema
            # modules' persist_final_*_json (see mirror_local_copy).
            mirror_local_copy(PORTFOLIO_BACKLOG_FILENAME, backlog)
    except Exception as e:
        return f"ERROR: Could not save Enterprise Agile Portfolio Backlog: {e}"

    if message.startswith("SUCCESS") and state is not None:
        state[STATE_KEY] = backlog
    return message


def load_portfolio_backlog(state: Optional[StateLike] = None) -> Dict[str, Any]:
    if state is not None:
        session_backlog = state.get(STATE_KEY)
        if isinstance(session_backlog, dict):
            result = dict(session_backlog)
            result.setdefault("status", "OK")
            return result

    if not config.is_mcp_mode():
        return _toolkit.load_portfolio_backlog(None)

    try:
        return _transport.call(
            "load_portfolio_backlog_json", {"session_id": paths.current_session_id()}
        )
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
