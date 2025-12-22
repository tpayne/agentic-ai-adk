# process_agents/design_agent.py
from google.adk.agents import LlmAgent
from typing import Dict, Any

def draft_process_workflow(sector: str, goals_csv: str, steps_description: str) -> str:
    """
    Formalizes a process workflow. 
    goals_csv: A comma-separated list of goals.
    """
    goals = [g.strip() for g in goals_csv.split(',')]
    return f"Workflow drafted for {sector} with {len(goals)} goals. Logic: {steps_description[:50]}..."

design_agent = LlmAgent(
    name='Design_Agent',
    model='gemini-2.0-flash-001', # Using 2.0 for stability
    description='Designs detailed step-by-step business process workflows.',
    instruction=(
        "Create a detailed workflow. Use 'draft_process_workflow'. "
        "Pass goals as a comma-separated string."
    ),
    tools=[draft_process_workflow]
)

