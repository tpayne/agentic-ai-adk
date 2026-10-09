"""CodedTool: load a previously-saved requirements summary.

Logic lives in process_toolkit.requirements_summary.requirements_summary
(shared with the ADK port); this is just the neuro-san wrapper threading
sly_data through as the session-local cache.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.requirements_summary.requirements_summary import load_requirements_summary


class LoadRequirementsSummaryCodedTool(CodedTool):
    """Loads the most relevant requirements summary -- this session's own,
    or the shared on-disk one."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_requirements_summary(sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
