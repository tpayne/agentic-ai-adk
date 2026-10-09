"""CodedTool: persist a structured requirements summary.

Logic lives in process_toolkit.requirements_summary.requirements_summary
(shared with the ADK port); this is just the neuro-san wrapper threading
sly_data through as the session-local cache.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.requirements_summary.requirements_summary import (
    save_requirements_summary,
    STATE_KEY as SLY_DATA_KEY,
)


class SaveRequirementsSummaryCodedTool(CodedTool):
    """Persists a requirements summary JSON object to disk."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        summary = args.get("summary")
        if not isinstance(summary, dict):
            return "ERROR: summary must be a JSON object."
        return save_requirements_summary(summary, sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
