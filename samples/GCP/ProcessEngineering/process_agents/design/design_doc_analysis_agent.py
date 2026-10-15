# process_agents/design_doc_analysis_agent.py

import os
import time
import logging
import random
from typing import Any, Optional

from google.adk.tools.tool_context import ToolContext

from ..common.utils import (
    save_iteration_feedback,
    load_directory_context,
    load_requirements_summary,
    getProperty,
)
from ..common.utils_agent import acquire_pipeline_lock_for_turn
from process_toolkit.run_lock import PipelineLockedError

logger = logging.getLogger("ProcessArchitect.DesignDocAnalysis")

def _remove_previous_approval_logs(tool_context: Optional[ToolContext] = None):
    """Silently remove output/approval.json and counter log, ignore exceptions.

    Also claims the shared output/ directory's pipeline lock (see
    process_toolkit.run_lock) before clearing anything -- see the parallel
    comment in process/analysis_agent.py's own _remove_previous_approval_logs
    for why this is the right choke point (both Full_Design_Doc_Pipeline and
    Update_Design_Doc_Pipeline route through this one function) and why
    acquire_pipeline_lock_for_turn (not a bare acquire_pipeline_lock call)
    is what makes token reuse here safe across a chat session with
    multiple, possibly-overlapping turns. doc_generation_agent.py's own
    create_standard_doc_from_file wrapper (this pipeline's genuine last
    step) releases it once the run truly completes."""
    try:
        acquire_pipeline_lock_for_turn("the design document pipeline", tool_context)
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

def log_analysis_metadata(industry_sector: str, goal_count: int, tool_context: Optional[ToolContext] = None):
    """Internal tool to track architectural extraction progress and clean environment."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    cleared = _remove_previous_approval_logs(tool_context)
    if cleared.startswith("ERROR"):
        return cleared
    logger.debug(f"Analysis Metadata - Sector: {industry_sector}, Goals Identified: {goal_count}.")
    return f"Analysis started for {industry_sector} with {goal_count} identified objectives."

def record_analysis_request(request: str, tool_context: Optional[ToolContext] = None):
    """Internal tool to log the original user request for traceability."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Original Analysis Request: {request}")
    cleared = _remove_previous_approval_logs(tool_context)
    if cleared.startswith("ERROR"):
        return cleared
    return "User request logged."

# -----------------------------
# DESIGN DOC ANALYSIS AGENT
# -----------------------------
from ..common.agent_wrappers import ProcessLlmAgent

design_doc_analysis_agent = ProcessLlmAgent(
    name="Design_Doc_Analysis_Agent",
    description="Performs deep architectural analysis on user prompts to extract requirements.",
    instruction_file="design/design_doc_analysis_agent.txt",
    tools=[
        record_analysis_request,
        log_analysis_metadata,
        load_directory_context,
        load_requirements_summary,
        save_iteration_feedback,
    ],
)