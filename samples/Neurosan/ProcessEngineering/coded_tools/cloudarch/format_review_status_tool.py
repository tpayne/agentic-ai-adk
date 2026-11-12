import asyncio
from typing import Any, Dict, List, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.feedback.iteration_feedback import format_review_status_summary


class FormatReviewStatusCodedTool(CodedTool):
    """Renders the CURRENT state of one or more feedback mailboxes
    (APPROVED, or every open issue's own persisted instruction text) into
    one deterministic plain-text summary, without draining any mailbox.

    Exists so a pipeline's own final "report the outcome" step relays this
    tool's actual output instead of free-paraphrasing Compliance_Agent's/
    Simulation_Agent's feedback from memory -- see format_review_status_
    summary's own docstring for the real production bug this guards
    against."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        channels: List[str] = args.get("channels") or ["compliance", "simulation"]
        return format_review_status_summary(channels=tuple(channels))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
