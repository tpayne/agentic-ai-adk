import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.drawio_persistence import load_drawio_xml
from coded_tools.common.cloudarch_drawio_session import claim_cloudarch_drawio_for_session


class LoadDrawioCodedTool(CodedTool):
    """Loads the most recently saved cloud architecture diagram, if any --
    and, on this chat session's first touch of the cloud architecture
    subsystem, adopts whatever is currently on disk as belonging to this
    session (without deleting anything -- a read-only question must
    never destroy data; see coded_tools.common.cloudarch_drawio_session's
    own docstring and coded_tools.cloudarch.reset_loop_state_tool's
    contrasting behavior for the generate/refine entry point)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        claim_cloudarch_drawio_for_session(sly_data)
        return load_drawio_xml()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
