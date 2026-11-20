"""Standalone "export the portfolio backlog/proposal response as a project
plan" support -- developed in tandem with samples/GCP/ProcessEngineering's
own Project_Plan_Export_Agent. Reads whatever portfolio_backlog.json/
proposal_response.json is already saved on disk; never re-runs analysis,
generation, or review, and never modifies the saved JSON itself -- same
discipline as process_visio_export's own standalone action."""

import asyncio
from typing import Any, Dict, List, Optional, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_interface.docgen.project_plan_export import (
    build_portfolio_backlog_project_plan,
    build_proposal_response_project_plan,
)


class ExportProjectPlanCodedTool(CodedTool):
    """Exports the current saved Enterprise Agile Portfolio Backlog or
    Proposal Response as an MSPDI project plan file. Pass
    {"schema_type": "portfolio_backlog"|"proposal_response", "start_date":
    optional ISO "YYYY-MM-DD", "resources": optional [{"name": str,
    "allocation_percent": number}, ...], "target_duration_weeks": optional
    number, "holiday_calendar": optional "uk"} -- the front-man determines
    schema_type (and extracts any of the other, genuinely optional fields
    from the user's own wording) the same way Visio_Export_Agent_Main
    determines schema_type for "export the diagram as Visio"."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        schema_type = args.get("schema_type")
        start_date: Optional[str] = args.get("start_date")
        resources: Optional[List[Dict[str, Any]]] = args.get("resources")
        target_duration_weeks: Optional[float] = args.get("target_duration_weeks")
        holiday_calendar: Optional[str] = args.get("holiday_calendar")
        if schema_type == "portfolio_backlog":
            return build_portfolio_backlog_project_plan(
                start_date, resources, target_duration_weeks, holiday_calendar,
            )
        if schema_type == "proposal_response":
            return build_proposal_response_project_plan(
                start_date, resources, target_duration_weeks, holiday_calendar,
            )
        return "ERROR: schema_type must be 'portfolio_backlog' or 'proposal_response'."

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
