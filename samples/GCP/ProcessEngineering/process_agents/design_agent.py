# process_agents/design_agent.py
from google.adk.agents import LlmAgent
import time

design_agent = LlmAgent(
    name='Design_Agent',
    model='gemini-2.0-flash-001',
    description='Architects detailed business process workflows.',
    instruction=(
        "You are a Process Engineer. Take the Requirements Specification and "
        "design a detailed, step-by-step business process. For every step, specify "
        "the Actor and the Action. Your output must include a logical sequence "
        "intended for both human reading and diagramming."
    )
)