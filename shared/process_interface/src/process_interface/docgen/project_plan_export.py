"""Switchable -- build_portfolio_backlog_project_plan/
build_proposal_response_project_plan render a real MSPDI project-plan XML
file from the session's persisted JSON baseline, so they follow
PROCESS_TOOLKIT_MODE exactly like docgen/vsdx_export.py's own
build_process_design_vsdx/build_cloudarch_vsdx.

Materialization is gated on the returned "project_plan" payload itself
being present (server.py's own export_project_plan tool sets it exactly
when a new project plan file was produced), NOT on matching a hand-copied
message prefix -- same reasoning as vsdx_export.py's own docstring.
"""

from typing import Any, Dict, List, Optional

from process_toolkit.docgen.project_plan_export import (
    PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME,
    PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME,
    build_portfolio_backlog_project_plan as _toolkit_build_portfolio_backlog_project_plan,
    build_proposal_response_project_plan as _toolkit_build_proposal_response_project_plan,
    portfolio_backlog_project_plan_exists,
    proposal_response_project_plan_exists,
)

from process_interface import _artifacts, _transport, config, paths

__all__ = [
    "build_portfolio_backlog_project_plan", "build_proposal_response_project_plan",
    "PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME", "PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME",
    "portfolio_backlog_project_plan_exists", "proposal_response_project_plan_exists",
]

# The *_exists() checks and filename constants stay always-local (same
# reasoning as vsdx_export.py's own identical checks) -- they read the LOCAL
# output dir, which materialize_one() already mirrors a successful MCP-mode
# export into, so there's nothing for these to redirect to the server for.


def build_portfolio_backlog_project_plan(
    start_date: Optional[str] = None,
    resources: Optional[List[Dict[str, Any]]] = None,
    target_duration_weeks: Optional[float] = None,
    holiday_calendar: Optional[str] = None,
) -> str:
    if not config.is_mcp_mode():
        return _toolkit_build_portfolio_backlog_project_plan(
            start_date, resources, target_duration_weeks, holiday_calendar,
        )

    try:
        result = _transport.call(
            "export_project_plan",
            {
                "schema_type": "portfolio_backlog",
                "start_date": start_date,
                "resources": resources,
                "target_duration_weeks": target_duration_weeks,
                "holiday_calendar": holiday_calendar,
                "session_id": paths.current_session_id(),
            },
        )
    except Exception as e:
        return f"ERROR: {e}"

    message = result["message"]
    if result.get("project_plan"):
        _artifacts.materialize_one(result.get("project_plan"))
    return message


def build_proposal_response_project_plan(
    start_date: Optional[str] = None,
    resources: Optional[List[Dict[str, Any]]] = None,
    target_duration_weeks: Optional[float] = None,
    holiday_calendar: Optional[str] = None,
) -> str:
    if not config.is_mcp_mode():
        return _toolkit_build_proposal_response_project_plan(
            start_date, resources, target_duration_weeks, holiday_calendar,
        )

    try:
        result = _transport.call(
            "export_project_plan",
            {
                "schema_type": "proposal_response",
                "start_date": start_date,
                "resources": resources,
                "target_duration_weeks": target_duration_weeks,
                "holiday_calendar": holiday_calendar,
                "session_id": paths.current_session_id(),
            },
        )
    except Exception as e:
        return f"ERROR: {e}"

    message = result["message"]
    if result.get("project_plan"):
        _artifacts.materialize_one(result.get("project_plan"))
    return message
