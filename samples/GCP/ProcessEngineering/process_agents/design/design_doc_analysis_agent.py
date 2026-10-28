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
    load_drawio,
    getProperty,
)
from ..common.utils_agent import acquire_pipeline_lock_for_turn, claim_cloudarch_drawio_readonly
from process_toolkit.run_lock import PipelineLockedError
from process_toolkit import paths as toolkit_paths

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

    approvalLog = toolkit_paths.output_path("approval.json")
    counterLog = toolkit_paths.output_path("stop_counter.json")
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
        load_drawio,
        save_iteration_feedback,
    ],
    # Same read-only session-ownership claim as CloudArch_Consultant_Agent/
    # etc. (see claim_cloudarch_drawio_readonly's own docstring) -- this
    # agent only ever READS an existing diagram via load_drawio, never
    # resets/deletes it, so claiming it must never be blocking or
    # destructive just because this happens to be the session's first
    # touch of the cloud-architecture subsystem.
    before_agent_callback=claim_cloudarch_drawio_readonly,
)