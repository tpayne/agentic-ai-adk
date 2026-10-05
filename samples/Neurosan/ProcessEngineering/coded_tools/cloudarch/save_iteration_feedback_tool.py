import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.iteration_feedback import save_iteration_feedback


class SaveIterationFeedbackCodedTool(CodedTool):
    """Writes the reviewer's verdict/feedback to the mailbox, updating the
    cumulative approval state for any approval marker found in it."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        feedback = args.get("feedback")
        channel = args.get("channel", "")
        return save_iteration_feedback(feedback, channel=channel)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
