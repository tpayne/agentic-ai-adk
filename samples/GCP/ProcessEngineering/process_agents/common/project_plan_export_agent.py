# process_agents/common/project_plan_export_agent.py
#
# Standalone, on-demand-only action -- export the current Enterprise Agile
# Portfolio Backlog or Proposal Response as an illustrative Microsoft
# Project / ProjectLibre interchange-format (MSPDI XML) project plan, from
# whatever is already saved on disk. NO re-analysis, NO backlog/proposal
# regeneration, and the saved data itself is never modified. Mirrors
# samples/Neurosan/ProcessEngineering's own project_plan_export.hocon
# network -- this is its domain-agnostic standalone-agent counterpart on
# the ADK side, the same way visio_export_agent.py's own Visio_Export_Agent
# is the ADK counterpart to process_visio_export.hocon's own
# Visio_Export_Agent_Main.
#
# Neither saved artifact has any real date/duration field -- the exported
# plan's durations are an illustrative planning estimate computed only at
# export time (see process_toolkit.docgen.project_plan_export's own
# module docstring), never written back into either saved JSON.

from typing import Any, Dict, List, Optional

from process_interface.docgen.project_plan_export import (
    build_portfolio_backlog_project_plan, build_proposal_response_project_plan,
)

from .agent_wrappers import ProcessAgent


def export_project_plan(
    schema_type: str,
    start_date: Optional[str] = None,
    resources: Optional[List[Dict[str, Any]]] = None,
    target_duration_weeks: Optional[float] = None,
    holiday_calendar: Optional[str] = None,
) -> str:
    """Exports the current saved Enterprise Agile Portfolio Backlog or Proposal Response as a real Microsoft Project / ProjectLibre interchange-format (MSPDI XML) project plan file, from whatever is already saved on disk. Never re-runs analysis, generation, or review, and never modifies the saved portfolio_backlog.json/proposal_response.json itself. schema_type ("portfolio_backlog" or "proposal_response") must be set -- determine it from the user's own request wording. start_date (ISO "YYYY-MM-DD") is optional and defaults to today. resources is an optional list of {"name": str, "allocation_percent": number} extracted from the user's own wording -- never fabricated -- rendered as MSPDI Resources/Assignments (every resource assigned to every leaf task, since neither saved artifact has any finer-grained role-to-task mapping). target_duration_weeks is an optional target project length in weeks, if the user stated one -- a post-hoc overrun check only, never compresses the schedule to fit. holiday_calendar, if set to "uk", marks real UK bank holidays as non-working so the scheduler skips them; no other value is supported."""
    if schema_type == "portfolio_backlog":
        return build_portfolio_backlog_project_plan(
            start_date, resources, target_duration_weeks, holiday_calendar,
        )
    if schema_type == "proposal_response":
        return build_proposal_response_project_plan(
            start_date, resources, target_duration_weeks, holiday_calendar,
        )
    return "ERROR: schema_type must be 'portfolio_backlog' or 'proposal_response'."


project_plan_export_agent = ProcessAgent(
    name="Project_Plan_Export_Agent",
    description=(
        "Exports the current Enterprise Agile Portfolio Backlog or Proposal Response as an "
        "illustrative Microsoft Project / ProjectLibre (MSPDI XML) project plan, from whatever is "
        "already saved on disk -- no re-analysis, no regeneration. Use ONLY on an explicit request "
        "naming a project plan / MS Project / ProjectLibre / Gantt chart."
    ),
    instruction_file="common/project_plan_export_agent.txt",
    tools=[export_project_plan],
)
