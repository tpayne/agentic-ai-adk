import asyncio
from typing import Any, Dict, List, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.feedback.iteration_feedback import format_review_status_summary


class FormatReviewStatusCodedTool(CodedTool):
    """Renders the CURRENT togaf_compliance feedback mailbox into one
    deterministic plain-text summary (APPROVED, or every open issue's own
    persisted instruction text), without draining the mailbox. Defaults
    specifically to ["togaf_compliance"] if channels is omitted."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        channels: List[str] = args.get("channels") or ["togaf_compliance"]
        return format_review_status_summary(channels=tuple(channels))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


__all__ = ["FormatReviewStatusCodedTool"]
