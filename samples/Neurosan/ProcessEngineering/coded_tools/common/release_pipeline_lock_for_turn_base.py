import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY


class ReleasePipelineLockForTurnCodedTool(CodedTool):
    """Safely releases THIS turn's own pipeline lock (acquired by this
    same turn's own reset_loop_state call) using the token already
    stashed in sly_data -- never force-clears, never touches a lock held
    by a genuinely different run (release_pipeline_lock only removes the
    lock file if its token still matches what sly_data recorded; a
    mismatch, or no token at all, is a safe no-op). This is the one
    action safe to take autonomously, without asking the user first,
    unlike clear_pipeline_lock_tool's unconditional force-clear (reserved
    for an explicit user request, since it cannot tell whose lock it
    would be clearing).

    Call this at any EARLY-STOP point in a generate/refine pipeline's own
    REQUIRED SEQUENCE that reports failure and stops BEFORE ever reaching
    the pipeline's genuine last step (generate_design_document/
    generate_process_document/zip_iac_files -- whichever already releases
    the lock on its own exit, success or failure, per that tool's own
    fix). Confirmed as a real production bug on the ADK port (see
    process_agents.common.utils_agent.release_pipeline_lock_after_run's
    own docstring) and independently confirmed to matter here too: a run
    that stops early -- e.g. Design_Doc_Analysis_Agent reports
    "REQUIREMENTS EXTRACTION FAILED" and the orchestrator is instructed
    to stop immediately rather than proceed -- never calls that final
    tool at all, so without an explicit release at the stop point itself,
    the lock stays held for up to run_lock.DEFAULT_STALE_AFTER_SECONDS
    (20 minutes), refusing every later request against the same output/
    directory with "another pipeline run is already in progress" even
    though nothing is actually still running."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
        stop_pipeline_lock_heartbeat(token)
        release_pipeline_lock(token)
        return {"status": "OK"}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
