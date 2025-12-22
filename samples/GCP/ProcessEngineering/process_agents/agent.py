# process_agents/agent.py
from google.adk.agents import SequentialAgent
import time
from .analysis_agent import analysis_agent
from .design_agent import design_agent
from .compliance_agent import compliance_agent
from .doc_gen_agent import doc_gen_agent

def request_human_approval(workflow_details: str) -> str:
    """Pauses execution for real human feedback."""
    print("\n" + "="*60)
    print("📋 PROPOSED BUSINESS PROCESS DESIGN:")
    print(workflow_details)
    print("="*60)
    feedback = input(">> Enter feedback to refine or press [Enter] to approve: ")
    if not feedback.strip():
        return "APPROVED"
    return f"REVISE: {feedback}"

# The SequentialAgent ensures data flows from one specialist to the next
root_agent = SequentialAgent(
    name="Process_Architect_Pipeline",
    sub_agents=[
        analysis_agent, 
        design_agent, 
        compliance_agent, 
        doc_gen_agent
    ],
    # Adding HITL logic as a post-processor or integrated step
    # depending on your specific ADK version's runner capabilities.
)

if __name__ == "__main__":
    print("Business Process Architect Pipeline Initialized.")
    time.sleep(2)