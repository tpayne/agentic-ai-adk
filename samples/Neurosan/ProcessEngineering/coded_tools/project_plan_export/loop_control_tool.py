import logging
from typing import Any, Dict, Union

from coded_tools.common.loop_control import LoopControlCodedTool as _SharedLoopControlCodedTool
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY
from process_interface.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat

logger = logging.getLogger("ProcessArchitect.LoopControl.ProjectPlanExport")

__all__ = ["LoopControlCodedTool"]


class LoopControlCodedTool(_SharedLoopControlCodedTool):
    """Same decision logic as the shared loop_control, plus release of the
    pipeline lock on a genuine 'STOP' verdict or exception.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
        try:
            result = super().invoke(args, sly_data)
        except Exception as error:
            logger.warning("ProjectPlanExport loop_control raised %s; releasing lock token=%s", error, token)
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)
            sly_data.pop(PIPELINE_LOCK_TOKEN_KEY, None)
            raise
        if isinstance(result, dict) and result.get("verdict") == "STOP":
            logger.info("ProjectPlanExport loop_control reached STOP; releasing lock token=%s", token)
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)
            sly_data.pop(PIPELINE_LOCK_TOKEN_KEY, None)
        return result

