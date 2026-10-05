import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.iteration_feedback import load_iteration_feedback


class LoadIterationFeedbackCodedTool(CodedTool):
    """Reads and drains the reviewer's feedback mailbox."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        channel = args.get("channel", "")
        return load_iteration_feedback(reset_data=True, channel=channel)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
