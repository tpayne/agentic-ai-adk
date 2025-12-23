# process_agents/compliance_agent.py
from google.adk.agents import LlmAgent

compliance_agent = LlmAgent(
    name='Compliance_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Audits processes against sector best practices.',
    instruction=(
        "You are a Compliance & Risk Officer. Review the designed workflow. "
        "Check for: "
        "1. Regulatory compliance (e.g., HIPAA for Health, KYC for Finance). "
        "2. Operational best practices (Six Sigma, Lean). 3. Security vulnerabilities. "
        "If issues are found, output 'REVISION REQUIRED' with details. "
        "If valid, output 'COMPLIANCE APPROVED' followed by the final workflow text."
        "If valid, output 'COMPLIANCE APPROVED' followed by the COMPLETE JSON object "
        "of the process design. Do not truncate the JSON; the Documentation Agent needs it all."
    )
)