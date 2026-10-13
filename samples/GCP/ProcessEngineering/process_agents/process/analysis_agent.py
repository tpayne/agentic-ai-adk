# process_agents/analysis_agent.py

import os
import time
import logging
import random
import json
from typing import Any

from ..common.utils import (
    save_iteration_feedback,
    load_directory_context,
    load_requirements_summary,
    getProperty,
)
from process_toolkit.run_lock import acquire_pipeline_lock, PipelineLockedError

logger = logging.getLogger("ProcessArchitect.Analysis")

def _remove_previous_approval_logs():
    # Called once at the start of a fresh analysis pass (via
    # log_analysis_metadata below) to clear approval/loop-counter state
    # left over from a PRIOR, unrelated pipeline run -- otherwise a stale
    # "APPROVED" status or loop count from before could make this run's
    # stop controller think review is already done before it has actually
    # happened. Silently remove output/approval.json, ignore exceptions.
    #
    # Also claims the shared output/ directory's pipeline lock (see
    # process_toolkit.run_lock) before clearing anything -- this is the
    # one call BOTH Full_Design_Pipeline (via log_analysis_metadata) and
    # Update_Design_Pipeline (via Process_Update_Analyst's own reuse of
    # log_analysis_metadata) already make exactly once per run, so it's
    # the right place to detect and refuse a second, concurrent run
    # against the same directory rather than letting it silently
    # interleave with and corrupt this one's state. A lock conflict
    # returns an error string instead of clearing anything, so a
    # genuinely-running other pipeline's state survives untouched.
    try:
        acquire_pipeline_lock("the process pipeline")
    except PipelineLockedError as e:
        return f"ERROR: {e}"

    approvalLog = "output/approval.json"
    counterLog = "output/stop_counter.json"
    try:
        if os.path.exists(approvalLog):
            os.remove(approvalLog)
        if os.path.exists(counterLog):
            os.remove(counterLog)
    except Exception:
        pass
    return "Previous approval logs cleared."

def log_analysis_metadata(sector: str, goal_count: int):
    """Internal tool to track extraction progress and CLEAN environment."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    cleared = _remove_previous_approval_logs()
    if cleared.startswith("ERROR"):
        return cleared
    logger.debug(f"Analysis Metadata - Sector: {sector}, Goals Identified: {goal_count}.")
    return f"Analysis started for {sector} with {goal_count} identified objectives."

def record_analysis_request(request: str):
    """Internal tool to log the original user request for traceability."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Original Analysis Request: {request}")
    cleared = _remove_previous_approval_logs()
    if cleared.startswith("ERROR"):
        return cleared
    return "User request logged."

# -----------------------------
# ANALYSIS AGENT
# -----------------------------
from ..common.agent_wrappers import ProcessLlmAgent

analysis_agent = ProcessLlmAgent(
    name="Analysis_Agent",
    description="Performs deep analysis of process descriptions.",
    instruction_file="process/analysis_agent.txt",   # auto-loads via load_instruction(...)
    tools=[
        log_analysis_metadata,
        record_analysis_request,
        load_directory_context,
        load_requirements_summary,
        save_iteration_feedback,
    ],
)