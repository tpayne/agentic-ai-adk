import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.feedback.iteration_feedback import reset_approval_state, reset_feedback_channels
from process_toolkit.run_lock import acquire_pipeline_lock, PipelineLockedError
from coded_tools.common.loop_control import reset_iteration_counter


class ResetLoopStateCodedTool(CodedTool):
    """Clears stale approval/iteration-counter/feedback-mailbox state left
    over from an earlier, unrelated pipeline run. Call once, as the very
    first action, at the start of handling a NEW generate-or-refine
    request -- not on every generate/review cycle within that same
    request.

    Feedback mailboxes specifically: a loop that stops at MAX_ITERATIONS
    immediately after a reviewer writes fresh feedback is never drained --
    the generator is never called again once the loop decides to stop --
    so without this, a later unrelated request's own generator could read
    and apply that stale review feedback the moment it checks the same
    channel.

    Also claims the shared output/ directory's pipeline lock (see
    process_toolkit.run_lock) -- this is the one call every one of this
    project's five generate/update pipelines already makes exactly once
    at the start of a run, so it's the right place to detect and refuse a
    second, concurrent run against the same directory rather than letting
    it silently interleave with and corrupt this one's state."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        try:
            acquire_pipeline_lock("a neuro-san pipeline")
        except PipelineLockedError as e:
            return {"status": "ERROR", "error": str(e)}
        reset_approval_state()
        reset_iteration_counter()
        reset_feedback_channels()
        return {"status": "OK"}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
