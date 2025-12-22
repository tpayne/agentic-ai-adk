# process_agents/design_agent.py
from google.adk.agents import LlmAgent
from typing import List, Dict, Any

def draft_process_workflow(sector: str, goals: List[str], steps_description: str) -> Dict[str, Any]:
    """
    Formalizes a process workflow into steps, decision points, and connections.
    """
    return {
        "sector": sector,
        "workflow_structure": "detailed",
        "steps_count": len(steps_description.split('\n')),
        "confirmation": "Workflow logic drafted. Ready for compliance review."
    }

design_agent = LlmAgent(
    name='Design_Agent',
    model='gemini-2.5-flash',
    description='Designs detailed step-by-step business process workflows.',
    instruction=(
        "Create a detailed business process based on the analysis. "
        "Define specific steps: Start -> Actions -> Decisions -> End. "
        "Ensure logical flow. Use 'draft_process_workflow' to confirm the structure."
    ),
    tools=[draft_process_workflow]
)
