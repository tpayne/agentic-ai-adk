import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.feedback.iteration_feedback import reset_approval_state, reset_feedback_channels
from process_toolkit.run_lock import acquire_pipeline_lock, start_pipeline_lock_heartbeat, PipelineLockedError
from coded_tools.common.loop_control import reset_iteration_counter
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY


class ResetLoopStateCodedTool(CodedTool):
    """Clears stale approval/iteration-counter/feedback-mailbox state left
    over from an earlier, unrelated pipeline run. Call once, as the very
    first action, at the start of handling a NEW generate-or-refine
    request -- not on every generate/review cycle within that same
    request.

    This is the generic base shared by process/process_update/design/
    design_update's own reset_loop_state_tool.py re-exports.
    coded_tools.cloudarch.reset_loop_state_tool defines its OWN subclass
    instead of re-exporting this one directly, since CloudArch also needs
    to reset output/cloudarch_drawio.xml on a session's first touch --
    logic that must NOT run for the other four pipelines, which have
    nothing to do with that file (see this module's own docstring
    history: reset_loop_state_tool.ResetLoopStateCodedTool used to be the
    single shared implementation here, re-exported verbatim by all five
    pipelines, which would have made a drawio reset added there fire for
    unrelated process/design runs too).

    Feedback mailboxes specifically: a loop that stops at MAX_ITERATIONS
    immediately after a reviewer writes fresh feedback is never drained --
    the generator is never called again once the loop decides to stop --
    so without this, a later unrelated request's own generator could read
    and apply that stale review feedback the moment it checks the same
    channel.

    Also claims the shared output/ directory's pipeline lock (see
    process_toolkit.run_lock) -- this is the one call every one of this
    project's five generate/update pipelines already makes exactly once
    at the start of a run (never a second time within the same run -- see
    each pipeline's own "Call reset_loop_state once" instruction), so
    it's the right place to detect and refuse a second, concurrent run
    against the same directory rather than letting it silently interleave
    with and corrupt this one's state. Always mints a FRESH token here
    (never reuses whatever is already in sly_data) -- sly_data is scoped
    to the whole chat SESSION, not to one request, so if a second,
    genuinely different request arrives in that same session while this
    one is still running, it must compete for the real lock on its own
    terms rather than silently inheriting this request's still-valid
    token and being waved through as "the same run". The token returned
    by acquire_pipeline_lock is stashed in sly_data under
    PIPELINE_LOCK_TOKEN_KEY purely so this pipeline's own finalize step
    (persist_final_json / persist_final_design_json /
    save_drawio_structured) can release it once THIS run genuinely
    completes -- not to be read back in on a later acquire.

    Also starts that token's background heartbeat (see
    process_toolkit.run_lock) -- there is no single tool call spanning a
    whole pipeline run to keep the lock fresh otherwise: a long single
    generate/review phase, or a pause awaiting the next piece of user
    input, could otherwise outlast DEFAULT_STALE_AFTER_SECONDS between
    this acquire and the eventual release, letting an unrelated
    concurrent run reclaim the lock while this one is still working."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        try:
            token = acquire_pipeline_lock("a neuro-san pipeline")
        except PipelineLockedError as e:
            return {"status": "ERROR", "error": str(e)}
        sly_data[PIPELINE_LOCK_TOKEN_KEY] = token
        start_pipeline_lock_heartbeat("a neuro-san pipeline", token)
        reset_approval_state()
        reset_iteration_counter()
        reset_feedback_channels()
        return {"status": "OK"}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
