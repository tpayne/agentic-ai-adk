# process_agents/analysis_agent.py
from google.adk.agents import LlmAgent
import time

def log_analysis_metadata(sector: str, goal_count: int):
    """Internal tool to track extraction progress."""
    time.sleep(2)
    return f"Analysis started for {sector} with {goal_count} identified objectives."

analysis_agent = LlmAgent(
    name='Analysis_Agent',
    model='gemini-2.0-flash-001',
    description='Performs deep analysis of process descriptions.',
    instruction=(
        "You are a Senior Business Analyst.\n\n"
        "Your task is to analyze the user's input and extract a complete Requirements Specification.\n"
        "This specification will be consumed by the Design Agent.\n\n"
        "You MUST output a single JSON object containing:\n"
        "- industry_sector\n"
        "- stakeholders\n"
        "- success_metrics\n"
        "- process_goals\n"
        "- constraints\n"
        "- assumptions\n"
        "- any other relevant requirements\n\n"
        "OUTPUT CONTRACT:\n"
        "- Output ONLY the final JSON object.\n"
        "- Do NOT output explanations or reasoning.\n"
        "- Do NOT ask the user questions.\n"
        "- Do NOT wait for confirmation.\n"
        "- Do NOT output partial JSON.\n\n"
        "TOOL USE:\n"
        "- You MAY call log_analysis_metadata(sector, goal_count) to record metadata.\n"
        "- If you call the tool, you MUST still output the final JSON object in the same turn.\n"
    ),
    tools=[log_analysis_metadata]
)
