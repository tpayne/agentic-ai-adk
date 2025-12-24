# process_agents/json_normalizer_agent.py
from google.adk.agents import LlmAgent
from google.genai import types
import os
import re
import traceback

import logging

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")

# -----------------------------
# Utility: Save raw JSON input
# -----------------------------
def log_agent_activity(message: str):
    """Internal tool to log agent progress for debugging."""
    logger.debug(f"--- [DIAGNOSTIC] JSON_Normalizer: {message} ---")
    return "Log recorded."

def save_raw_data_to_json(json_content: str) -> str:
    """
    Save the full JSON string to a local file for processing.
    The content may come wrapped in ```json fences; we strip those.

    EXPECTATION:
    - json_content is already a normalized, document-ready JSON string.
    """
    try:
        logger.info("Saving normalized JSON to file...")
        os.makedirs("output", exist_ok=True)
        old_path = "output/process_data.json"
        clean_json = re.sub(
            r'^```json\s*|```$',
            '',
            json_content.strip(),
            flags=re.MULTILINE
        )

        new_path = "output/process_data.json"
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(clean_json)

        return new_path

    except Exception:
        traceback.print_exc()
        return "ERROR: Failed to save JSON"


# -----------------------------
# JSON Normalizer Agent
# -----------------------------

json_normalizer_agent = LlmAgent(
    name="JSON_Normalizer_Agent",
    model="gemini-2.0-flash-001",
    description="Normalizes arbitrary business process JSON into a stable enriched schema.",
    instruction=(
        "You are a Senior Process Architect. Your ONLY goal is to call the 'save_raw_data_to_json' tool.\n\n"
        
        "PHASE 1: LOGGING\n"
        "Immediately call log_agent_activity('Starting Enrichment and Schema Mapping').\n\n"

        "PHASE 2: ENRICHMENT & MAPPING\n"
        "Transform the input data into the following schema. You MUST expand every 'description' "
        "and the 'introduction' into detailed paragraphs (Enrichment).\n"
        "{\n"
        "  \"process_name\": string, \"version\": string, \"introduction\": string,\n"
        "  \"stakeholders\": [], \"process_steps\": [], \"tools_summary\": {},\n"
        "  \"metrics\": [], \"reporting_and_analytics\": {}, \n"
        "  \"system_requirements\": [], \"appendix\": {}\n"
        "}\n\n"

        "PHASE 3: EXECUTION\n"
        "- Call 'save_raw_data_to_json' with the resulting JSON object.\n"
        "- NO natural language output. NO markdown fences (```json).\n"
        "- Your turn is complete ONLY after calling the tool."
    ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.0,
        top_p=1,
    ),
    tools=[save_raw_data_to_json, log_agent_activity]
)