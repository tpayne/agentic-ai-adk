import asyncio
from typing import Any, Dict, Union

from process_toolkit.drawio.persistence import reset_drawio_xml

from coded_tools.common.reset_loop_state_base import ResetLoopStateCodedTool as _BaseResetLoopStateCodedTool
from coded_tools.common.cloudarch_drawio_session import claim_cloudarch_drawio_for_session


class ResetLoopStateCodedTool(_BaseResetLoopStateCodedTool):
    """CloudArch's own reset step: everything
    coded_tools.common.reset_loop_state_base.ResetLoopStateCodedTool
    already does (claim the pipeline lock, clear stale approval/
    iteration-counter/feedback-mailbox state), PLUS: on this chat
    session's first touch of the cloud architecture subsystem, also
    clears any existing output/cloudarch_drawio.xml -- it could only be a
    stale leftover from a different, unrelated session, since this
    session has never touched it before. Otherwise a brand-new session's
    very first "generate a cloud architecture" request could silently be
    treated as a refinement of someone else's diagram.

    See coded_tools.common.cloudarch_drawio_session's own docstring for
    why this is safe to do here (a generate/refine entry point) but NOT
    inside the read-only query agents' own load_drawio tool."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        result = super().invoke(args, sly_data)
        if isinstance(result, dict) and result.get("status") == "OK":
            if claim_cloudarch_drawio_for_session(sly_data):
                reset_drawio_xml()
        return result

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
