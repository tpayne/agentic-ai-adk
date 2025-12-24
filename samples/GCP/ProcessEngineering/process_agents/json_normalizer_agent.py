# process_agents/json_normalizer_agent.py
from google.adk.agents import LlmAgent
import os
import re
import traceback

import logging

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")

# -----------------------------
# Utility: Save raw JSON input
# -----------------------------

def save_raw_data_to_json(json_content: str) -> str:
    """
    Save the full JSON string to a local file for processing.
    The content may come wrapped in ```json fences; we strip those.

    EXPECTATION:
    - json_content is already a normalized, document-ready JSON string.
    """
    try:
        logger.info("Normalization complete. Writing state to output/process_data.json")
        print(f"Attempting to save normalized JSON data...")
        os.makedirs("output", exist_ok=True)
        old_path = "output/process_data.json"
        clean_json = re.sub(
            r'^```json\s*|```$',
            '',
            json_content.strip(),
            flags=re.MULTILINE
        )

        path = "output/process_data.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(clean_json)

        return path

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
        "You are a Process Data Normalization Specialist. "
        "Your EXCLUSIVE goal is to transform raw business process data into a stable schema "
        "and save it using the 'save_raw_data_to_json' tool.\n\n"

        "TOOL CALL PAYLOAD REQUIREMENTS:\n"
        "The 'json_content' argument of your tool call MUST be a single, complete JSON object "
        "following this schema:\n"
        "{\n"
        "  \"process_name\": string,\n"
        "  \"version\": string,\n"
        "  \"introduction\": string,\n"
        "  \"stakeholders\": [...],\n"
        "  \"process_steps\": [...],\n"
        "  \"tools_summary\": {...},\n"
        "  \"metrics\": [...],\n"
        "  \"reporting_and_analytics\": {...},\n"
        "  \"system_requirements\": [...],\n"
        "  \"appendix\": {...}\n"
        "}\n\n"

        "JSON STRICTNESS (MANDATORY):\n"
        "- Argument must be valid, parseable JSON (json.loads() compatible).\n"
        "- Use double quotes for all keys and strings. No single quotes.\n"
        "- Do NOT output Python dictionaries; Do NOT use markdown fences (```json).\n\n"

        "CONTENT QUALITY:\n"
        "- Enrich vague sections with professional, auditable detail.\n"
        "- Organize steps into a logical, sequential workflow.\n"
        "- Map any content that cannot be categorized into the \"appendix\".\n\n"

        "EXECUTION RULES:\n"
        "- You MUST NOT respond with natural language or the JSON text itself.\n"
        "- You MUST output ONLY the tool call to 'save_raw_data_to_json'.\n"
        "- Place the entire normalized JSON object into the 'json_content' parameter.\n"
        "- After the tool call is emitted, you MUST stop immediately."
    ),
    tools=[save_raw_data_to_json]
)
