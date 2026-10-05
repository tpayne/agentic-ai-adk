import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.iteration_feedback import reset_approval_state
from coded_tools.common.loop_control import reset_iteration_counter


class ResetLoopStateCodedTool(CodedTool):
    """Clears stale approval/iteration-counter state left over from an
    earlier, unrelated pipeline run. Call once, as the very first action,
    at the start of handling a NEW generate-or-refine request -- not on
    every generate/review cycle within that same request."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        reset_approval_state()
        reset_iteration_counter()
        return {"status": "OK"}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
