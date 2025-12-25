# process_agents/json_review_agent.py
from google.adk.agents import LlmAgent
import logging

logger = logging.getLogger("ProcessArchitect.JsonReview")

def log_agent_activity(message: str):
    """Internal tool to log agent progress for debugging."""
    logger.info(f"--- [DIAGNOSTIC] JSON_Reviewer: {message} ---")
    return "Log recorded."

# -----------------------------
# JSON REVIEW AGENT
# -----------------------------
json_review_agent = LlmAgent(
    name='Json_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Review JSON for validity, compliance, and best practices.',
    instruction=(
        "You are a Json Review Officer.\n\n"
        "Your task is to review the normalized JSON produced by the JSON Normalizer Agent and provide feedback and corrections.\n"

        "You operate in three strict steps:\n\n"

        "STEP 1: LOGGING\n"
        "Immediately CALL the tool log_agent_activity('Starting JSON review process').\n\n"

        "STEP 2: JSON REVIEW\n"
        "Check for:\n"
        "1. Valid JSON structure and schema adherence.\n"
        "2. Ensuring all required fields are present.\n"
        "3. Ensuring the logical consistency of the data.\n"
        "4. Ensuring data quality standards are met in that all descriptions are complete and accurate.\n"
        "5. Ensuring processes are thoroughly documented.\n\n"

        "STEP 3: OUTPUT CONTRACT:\n"
        "- If issues exist, output EXACTLY:\n"
        "    REVISION REQUIRED\n"
        "    <JSON object describing required changes>\n\n"
        "- If the JSON is valid, output EXACTLY:\n"
        "    JSON APPROVED\n"
        "    <COMPLETE normalized JSON object>\n\n"
        "- Do NOT output commentary, reasoning, or prose.\n"
        "- Do NOT output partial JSON.\n"
        "- Do NOT ask the user questions.\n"
        "- Do NOT wait for confirmation.\n"
        "- The JSON must be complete and untruncated.\n"
    ),
    tools=[log_agent_activity]
)
