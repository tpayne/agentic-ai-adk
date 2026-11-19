# process_agents/itsm/analysis_agent.py
#
# Requirements-extraction stage for Full_ITSM_Pipeline, mirroring
# process/analysis_agent.py's own shape (clear stale approval/loop-counter
# state and claim the shared output/ directory's pipeline lock before the
# generate/review loop starts) -- NOT togaf_pipeline_agent.py's lighter
# before_agent_callback-only reset, since ITSM (like process) has its own
# dedicated analysis agent to host this in.

import os
import time
import logging
import random
from typing import Optional

from google.adk.tools.tool_context import ToolContext

from ..common.utils import (
    save_iteration_feedback,
    load_directory_context,
    load_requirements_summary,
    getProperty,
)
from ..common.utils_agent import acquire_pipeline_lock_for_turn
from process_interface.run_lock import PipelineLockedError
from process_interface import paths as toolkit_paths
from process_interface.feedback.iteration_feedback import reset_feedback_channels

logger = logging.getLogger("ProcessArchitect.ItsmAnalysis")


def _remove_previous_itsm_approval_logs(tool_context: Optional[ToolContext] = None):
    """Claims this turn's pipeline lock (see acquire_pipeline_lock_for_turn's
    own docstring) and clears stale output/approval.json / stop_counter.json
    left over from an earlier, unrelated pipeline run -- same reasoning as
    process/analysis_agent.py's own _remove_previous_approval_logs.

    Also clears the itsm_analysis/itsm_compliance/itsm_simulation feedback
    mailboxes via reset_feedback_channels() -- see
    togaf_pipeline_agent.py's own _reset_togaf_approval_state docstring for
    the gap this closes: without it, a run that ends right after
    ITSM_Compliance_Agent/ITSM_Simulation_Agent write feedback would leave
    that feedback sitting in the mailbox, and a LATER, unrelated ITSM
    request in a NEW turn would find it and incorrectly treat a fresh
    generate request as a revision pass."""
    try:
        acquire_pipeline_lock_for_turn("the ITSM pipeline", tool_context)
    except PipelineLockedError as e:
        return f"ERROR: {e}"

    approval_log = toolkit_paths.output_path("approval.json")
    counter_log = toolkit_paths.output_path("stop_counter.json")
    try:
        if os.path.exists(approval_log):
            os.remove(approval_log)
        if os.path.exists(counter_log):
            os.remove(counter_log)
    except Exception:
        pass

    reset_feedback_channels()
    return "Previous approval logs cleared."


def log_itsm_analysis_metadata(sector: str, goal_count: int, tool_context: Optional[ToolContext] = None):
    """Internal tool to track extraction progress and CLEAN environment."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    cleared = _remove_previous_itsm_approval_logs(tool_context)
    if cleared.startswith("ERROR"):
        return cleared
    logger.debug(f"ITSM Analysis Metadata - Sector: {sector}, Goals Identified: {goal_count}.")
    return f"ITSM analysis started for {sector} with {goal_count} identified objectives."


def record_itsm_analysis_request(request: str, tool_context: Optional[ToolContext] = None):
    """Internal tool to log the original user request for traceability."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Original ITSM Analysis Request: {request}")
    cleared = _remove_previous_itsm_approval_logs(tool_context)
    if cleared.startswith("ERROR"):
        return cleared
    return "User request logged."


# -----------------------------
# ITSM ANALYSIS AGENT
# -----------------------------
from ..common.agent_wrappers import ProcessLlmAgent

itsm_analysis_agent = ProcessLlmAgent(
    name="ITSM_Analysis_Agent",
    description="Extracts structured ITSM requirements (services, roles, incident/problem/change/request processes, SLAs, a light CMDB, RACI) from a request.",
    instruction_file="itsm/analysis_agent.txt",
    tools=[
        log_itsm_analysis_metadata,
        record_itsm_analysis_request,
        load_directory_context,
        load_requirements_summary,
        save_iteration_feedback,
    ],
)
