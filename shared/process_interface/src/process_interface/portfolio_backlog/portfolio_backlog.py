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
from process_interface.docgen.project_plan_export import (
    PORTFOLIO_BACKLOG_PERT_CPM_FILENAME,
    PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME,
    portfolio_backlog_project_plan_exists,
)

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
        message = _toolkit.save_portfolio_backlog(backlog, state)
    else:
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

    # Covers both a real update AND a from-scratch creation that happens to
    # overwrite a backlog a project plan was already exported from -- either
    # way the already-exported MSPDI XML (and its companion PERT/CPM
    # diagram, always written together -- see docgen.project_plan_export's
    # own _build_and_write_pert_cpm) now reflects stale content, and nothing
    # in this codebase re-exports either automatically (project_plan_export
    # is deliberately export-only, see its own module docstring). A single
    # portfolio_backlog_project_plan_exists() check is enough to know the
    # PERT/CPM file exists too, since the two are never written separately.
    if message.startswith("SUCCESS") and portfolio_backlog_project_plan_exists():
        message += (
            " NOTE: a project plan and its PERT/CPM diagram were previously exported from this "
            f"backlog ({PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME} / {PORTFOLIO_BACKLOG_PERT_CPM_FILENAME}) "
            "-- neither was regenerated and both may now be stale relative to this change; export "
            "the project plan again if you'd like them to reflect it."
        )
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
