import asyncio
import time
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.run_lock import force_clear_pipeline_lock


class ClearPipelineLockCodedTool(CodedTool):
    """Forcibly clears the shared output/ directory's pipeline lock, if
    one is currently held -- regardless of how old it is or which run
    holds it.

    Call this ONLY when the user explicitly asks to clear, reset, or
    unstick a pipeline lock -- e.g. they saw "Another pipeline run ...
    is already in progress" and are confident nothing is actually still
    running. NEVER call this as a troubleshooting guess, and never in
    response to a request that is just a normal pipeline run (that
    always goes through the real pipeline tools, not this one).
    Forcibly clearing a lock a genuinely still-running pipeline holds
    can let two runs interleave their writes to the same output/
    directory and corrupt it -- that judgment call belongs to the user,
    since only they know whether another request of theirs is actually
    still in flight elsewhere.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        cleared = force_clear_pipeline_lock()
        if cleared is None:
            return {"status": "OK", "cleared": False, "message": "No pipeline lock is currently held -- there was nothing to clear."}

        label = cleared.get("label", "an unknown pipeline")
        started_at = cleared.get("started_at")
        age_str = ""
        if isinstance(started_at, (int, float)):
            age_minutes = (time.time() - started_at) / 60
            age_str = f", held for about {age_minutes:.1f} minute{'s' if abs(age_minutes - 1) > 0.05 else ''}"
        return {
            "status": "OK",
            "cleared": True,
            "message": f"Cleared the pipeline lock (was held by '{label}'{age_str}). You can retry your request now.",
        }

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
