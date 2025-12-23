# process_agents/design_agent.py
from google.adk.agents import LlmAgent
import time

design_agent = LlmAgent(
    name='Design_Agent',
    model='gemini-2.0-flash-001',
    description='Architects detailed business process workflows.',
    instruction=(
        "You are a Process Engineer. Create a detailed process from the initial requirements. "
        "CRITICAL: If you receive feedback starting with 'REVISION REQUIRED', you must update "
        "your previous design to address those specific comments."
        "Only output the final result. Do not provide internal monologue or draft JSON unless "
        "specifically required for a tool call."
    )
)