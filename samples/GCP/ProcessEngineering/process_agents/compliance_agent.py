# process_agents/compliance_agent.py
from google.adk.agents import LlmAgent
import logging

logger = logging.getLogger("ProcessArchitect.Compliance")

compliance_agent = LlmAgent(
    name='Compliance_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Audits processes against sector best practices.',
    instruction=(
        "You are a Compliance & Risk Officer.\n\n"
        "Your task is to review the process JSON produced by the Design Agent.\n"
        "Check for:\n"
        "1. Regulatory compliance (HIPAA, GDPR, PCI DSS, KYC, etc.).\n"
        "2. Operational best practices (Lean, Six Sigma, ITIL).\n"
        "3. Security vulnerabilities.\n\n"
        "OUTPUT CONTRACT:\n"
        "- If issues exist, output EXACTLY:\n"
        "    REVISION REQUIRED\n"
        "    <JSON object describing required changes>\n\n"
        "- If the design is valid, output EXACTLY:\n"
        "    COMPLIANCE APPROVED\n"
        "    <COMPLETE JSON object of the approved design>\n\n"
        "- Do NOT output commentary, reasoning, or prose.\n"
        "- Do NOT output partial JSON.\n"
        "- Do NOT ask the user questions.\n"
        "- Do NOT wait for confirmation.\n"
        "- The JSON must be complete and untruncated.\n"
    )
)
