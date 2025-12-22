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
        "You are a Senior Business Analyst. Analyze the input to extract: "
        "1. Precise Industry Sector. 2. All Stakeholders/Actors. 3. Defined Success Metrics. "
        "Your output must be a 'Requirements Specification' used by the Design Agent."
    ),
    tools=[log_analysis_metadata]
)