"""Tool to parse and inspect exported project plan metrics (MSPDI XML) for quality review."""

import asyncio
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool
from process_interface import paths as toolkit_paths
from process_interface.docgen.project_plan_export import (
    PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME,
    PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME,
    parse_mspdi_project,
)


class InspectProjectPlanCodedTool(CodedTool):
    """Parses and returns structured quality and schedule metrics for the exported project plan (MSPDI XML).
    schema_type is 'portfolio_backlog' or 'proposal_response'.
    Returns structured metrics: start_date, finish_date, total_tasks, summary_tasks, leaf_tasks,
    total_resources, total_assignments, total_cost, and phase breakdown with concurrency info.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        schema_type = args.get("schema_type", "portfolio_backlog")
        filename = (
            PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME
            if schema_type == "portfolio_backlog"
            else PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME
        )
        plan_path = toolkit_paths.output_path(filename)
        if not os.path.exists(plan_path):
            return {
                "status": "NOT_FOUND",
                "message": f"No exported project plan found at {plan_path}. Run export_project_plan first.",
            }

        parsed = parse_mspdi_project(plan_path)
        if not parsed:
            return {"status": "ERROR", "message": f"Failed to parse MSPDI project plan at {plan_path}."}

        tasks = parsed.get("tasks", [])
        summary_tasks = [t for t in tasks if t.get("is_summary")]
        leaf_tasks = [t for t in tasks if not t.get("is_summary")]
        resources = parsed.get("resources", [])
        assignments = parsed.get("assignments", [])

        phases = []
        for st in summary_tasks:
            phases.append({
                "id": st.get("id"),
                "name": st.get("name"),
                "start": st.get("start"),
                "finish": st.get("finish"),
                "duration_days": st.get("duration_days"),
                "predecessors": st.get("predecessors", []),
            })

        return {
            "status": "OK",
            "file": plan_path,
            "title": parsed.get("title"),
            "start_date": parsed.get("start_date"),
            "finish_date": parsed.get("finish_date"),
            "total_tasks": len(tasks),
            "summary_tasks_count": len(summary_tasks),
            "leaf_tasks_count": len(leaf_tasks),
            "total_resources": len(resources),
            "total_assignments": len(assignments),
            "total_cost": parsed.get("total_cost", 0.0),
            "phases": phases,
            "resources": [
                {"id": r.get("id"), "name": r.get("name"), "max_units": r.get("max_units")}
                for r in resources
            ],
        }

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
