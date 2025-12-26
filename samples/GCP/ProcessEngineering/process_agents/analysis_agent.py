# process_agents/analysis_agent.py
from google.adk.agents import LlmAgent
import os
import time
import logging

logger = logging.getLogger("ProcessArchitect.Analysis")

def log_analysis_metadata(sector: str, goal_count: int):
    """Internal tool to track extraction progress and CLEAN environment."""
    time.sleep(1)
    logger.info(f"Analysis Metadata - Sector: {sector}, Goals Identified: {goal_count}.")
    return f"Analysis started for {sector} with {goal_count} identified objectives."

def record_analysis_request(request: str):
    """Internal tool to log the original user request for traceability."""
    time.sleep(1)
    logger.info(f"Original Analysis Request: {request}")
    return "User request logged."

# -----------------------------
# ANALYSIS AGENT
# -----------------------------
analysis_agent = LlmAgent(
    name='Analysis_Agent',
    model='gemini-2.0-flash-001',
    description='Performs deep analysis of process descriptions.',
    instruction=(
        "You are a Senior Business Analyst. You operate in three strict steps:\n\n"
        
        "STEP 1: TRACEABILITY (MANDATORY)\n"
        "Your very first action MUST be to CALL the tool 'record_analysis_request' with the user's raw input.\n\n"
        
        "STEP 2: METADATA (MANDATORY)\n"
        "Immediately after, CALL the tool 'log_analysis_metadata' with the identified sector and goal count.\n\n"

        "STEP 3: REQUIREMENTS EXTRACTION\n"
        "Generate a single JSON object containing:\n"
        "- industry_sector\n"
        "- stakeholders and their responsibilities\n"
        "- success_metrics\n"
        "- process_goals\n"
        "- process_steps with detailed descriptions\n"
        "- system_requirements\n"
        "- reporting_and_analytics needs\n"
        "- constraints\n"
        "- assumptions\n\n"
        
        "OUTPUT CONTRACT:\n"
        "- You MUST call both tools before providing the JSON.\n"
        "- Output ONLY the final JSON object after tool results are returned.\n"
        "- Do NOT output explanations or reasoning.\n"
        "- Do NOT ask questions."
    ),
    tools=[log_analysis_metadata, record_analysis_request],
)
