"""CodedTool: apply a targeted patch to the saved requirements summary.

Logic lives in process_toolkit.requirements_summary.requirements_summary
(shared with the ADK port); this is just the neuro-san wrapper threading
sly_data through as the session-local cache. Used by Requirements_
Reviewer_Agent to apply corrections it finds during a quality audit,
when the user's own request explicitly asked for fixes.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.requirements_summary.requirements_summary import update_requirements_summary


class UpdateRequirementsSummaryCodedTool(CodedTool):
    """Shallow-merges a patch onto the saved requirements summary and
    re-persists it."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        patch = args.get("patch")
        if not isinstance(patch, dict):
            return "ERROR: patch must be a JSON object."
        return update_requirements_summary(patch, sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
