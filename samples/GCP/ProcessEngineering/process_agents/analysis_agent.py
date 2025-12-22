# process_agents/analysis_agent.py
from google.adk.agents import LlmAgent
from typing import Dict, Any

def analyze_process_requirements(raw_text: str) -> Dict[str, Any]:
    """
    Analyzes raw text to extract key process metadata.
    Returns structured dictionary with sector, actors, and high-level goals.
    """
    # In a real scenario, this might use NLP libraries or specific regex.
    # Here we simulate structure for the LLM to populate via its reasoning.
    return {
        "status": "analyzed",
        "input_length": len(raw_text),
        "note": "Analysis successful. LLM will structure the output in the conversation context."
    }

analysis_agent = LlmAgent(
    name='Analysis_Agent',
    model='gemini-2.5-flash',
    description='Analyzes unstructured business descriptions to identify goals, actors, and industry sector.',
    instruction=(
        "Analyze the provided text. Identify: "
        "1. The Industry Sector (e.g., Finance, Healthcare, Retail). "
        "2. The Primary Actors (Who is involved?). "
        "3. The High-Level Goals (What is the outcome?). "
        "Return this as a structured summary for the Design Agent."
    ),
    tools=[analyze_process_requirements]
)
