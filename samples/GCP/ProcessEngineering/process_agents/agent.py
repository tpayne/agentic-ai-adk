# process_agents/agent.py
"""
Root ADK Agent: Business Process Architect
Orchestrates: Analysis -> Design -> Compliance Review -> Documentation
Includes Human-in-the-Loop (HITL) feedback mechanism.
"""
from google.adk.agents import LlmAgent
import logging
import os
import sys

# -----------------------------------------------------------------------------
# Logging Setup
# -----------------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    lvl = os.getenv('LOGLEVEL', 'INFO').upper()
    logger.setLevel(lvl)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s'))
        logger.addHandler(handler)
    return logger

logger = get_logger('process_root')

# -----------------------------------------------------------------------------
# Sub-Agent Imports
# -----------------------------------------------------------------------------
from .analysis_agent import analysis_agent
from .design_agent import design_agent
from .compliance_agent import compliance_agent
from .doc_gen_agent import doc_gen_agent

# -----------------------------------------------------------------------------
# HITL Tool
# -----------------------------------------------------------------------------
def request_human_feedback(question: str, context_summary: str) -> str:
    """
    Pauses execution to request feedback from the human user.
    Useful for refining process steps or approving compliance checks.
    """
    print("\n" + "="*60)
    print(f"🤖 AGENT REQUESTS FEEDBACK: {question}")
    print(f"📄 CONTEXT: {context_summary}")
    print("="*60 + "\n")
    
    # In a containerized API environment, this might be a webhook. 
    # For CLI/local runs, we use standard input.
    try:
        feedback = input(">> Enter your feedback (or press Enter to approve): ")
        if not feedback.strip():
            return "Approved by human user."
        return f"User Feedback: {feedback}"
    except EOFError:
        return "No feedback provided (Non-interactive mode)."

# -----------------------------------------------------------------------------
# Root Agent Definition
# -----------------------------------------------------------------------------
root_agent = LlmAgent(
    name='Process_Architect_Root',
    model='gemini-2.0-flash-001',
    description='Lead Architect orchestrating business process analysis, design, and documentation.',
    instruction=(
        "You are the Lead Process Architect. "
        "1. Delegate incoming descriptions to 'Analysis_Agent' to structure the intent and identify the sector. "
        "2. Send the structured intent to 'Design_Agent' to create a detailed workflow. "
        "3. Send the workflow to 'Compliance_Review_Agent'. If issues are found, loop back to Design. "
        "4. CRITICAL: Before finalizing, use 'request_human_feedback' to show the user the summary and ask for approval. "
        "5. Once approved, delegate to 'Documentation_Agent' to generate the .docx and Diagram. "
        "6. Confirm the filenames of the generated assets to the user."
    ),
    tools=[request_human_feedback],
    sub_agents=[analysis_agent, design_agent, compliance_agent, doc_gen_agent]
)

if __name__ == "__main__":
    # Simple CLI entry point for testing
    print("Process Architect Initialized. Waiting for prompt...")
    # This would typically be invoked by the ADK runner
