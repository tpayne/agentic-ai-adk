# process_agents/compliance_agent.py
from google.adk.agents import LlmAgent
from typing import Dict, Any

def check_sector_compliance(sector: str, process_details: str) -> Dict[str, Any]:
    """
    Simulates a compliance check against a knowledge base of best practices.
    """
    warnings = []
    
    # Simple rule-based heuristics for demonstration
    if sector.lower() in ['finance', 'banking'] and 'audit' not in process_details.lower():
        warnings.append("Missing 'Audit Trail' or 'Logging' step required for Finance sector.")
    
    if sector.lower() in ['healthcare', 'medical'] and 'privacy' not in process_details.lower():
        warnings.append("Missing 'Patient Privacy/HIPAA' check required for Healthcare.")
        
    status = "Approved" if not warnings else "Review Needed"
    
    return {
        "sector": sector,
        "status": status,
        "warnings": warnings,
        "recommendation": "Proceed" if status == "Approved" else "Refine Design"
    }

compliance_agent = LlmAgent(
    name='Compliance_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Reviews process designs for sector-specific compliance and best practices.',
    instruction=(
        "Review the drafted workflow. Use 'check_sector_compliance'. "
        "If the tool returns warnings, summarize them and recommend changes to the Design Agent. "
        "If Approved, authorize the move to Documentation."
    ),
    tools=[check_sector_compliance]
)
