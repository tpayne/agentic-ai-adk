from typing import Any, Dict, Union

from coded_tools.common.loop_control import LoopControlCodedTool as _SharedLoopControlCodedTool
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY
from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat

__all__ = ["LoopControlCodedTool"]


class LoopControlCodedTool(_SharedLoopControlCodedTool):
    """Same decision logic as every other network's loop_control, plus one
    CloudArch-specific addition: on a genuine "STOP" verdict, releases the
    shared output/ directory's pipeline lock (see process_toolkit.run_lock).

    This is cloudarch.hocon's OWN finalize point -- unlike process/design,
    whose front-man has further steps (subprocess expansion, diagram/doc
    generation) AFTER loop_control's STOP (where releasing here would be
    premature), cloudarch.hocon's own sequence ends at step 5 (plain-prose
    reporting, no further tool call) right after this STOP -- see
    cloudarch.hocon's own "REQUIRED SEQUENCE" comment. That's why this
    behavior lives in cloudarch's own per-network shim rather than the
    shared coded_tools.common.loop_control.LoopControlCodedTool every
    other network re-exports unwrapped."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        result = super().invoke(args, sly_data)
        if isinstance(result, dict) and result.get("verdict") == "STOP":
            token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)
        return result
