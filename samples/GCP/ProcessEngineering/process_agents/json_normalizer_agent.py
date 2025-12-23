# process_agents/json_normalizer_agent.py
from google.adk.agents import LlmAgent
import os
import re
import traceback

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
        os.makedirs("output", exist_ok=True)

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
        "You are a Process Data Normalization Specialist.\n\n"
        "Your task is to take the raw, free-form business process JSON provided by the user "
        "and transform it into a normalized, enriched, document-ready JSON schema.\n\n"

        "OUTPUT CONTRACT:\n"
        "- You MUST produce a single, complete JSON object following this flexible schema:\n"
        "  {\n"
        "    \"process_name\": string,\n"
        "    \"version\": string,\n"
        "    \"introduction\": string,\n"
        "    \"stakeholders\": [...],\n"
        "    \"process_steps\": [...],\n"
        "    \"tools_summary\": {...},\n"
        "    \"metrics\": [...],\n"
        "    \"reporting_and_analytics\": {...},\n"
        "    \"system_requirements\": [...],\n"
        "    \"appendix\": {...}\n"
        "  }\n\n"

        "- You MUST preserve all meaningful content from the original JSON.\n"
        "- You MUST enrich vague descriptions, add a document-ready introduction, "
        "  and clarify step names.\n"
        "- Any content that cannot be mapped MUST go into \"appendix\".\n"
        "- You MUST NOT output the JSON to the user. Instead, you MUST immediately call "
        "  save_raw_data_to_json with the FULL normalized JSON string.\n"
        "- Do NOT output natural language. Do NOT ask the user anything.\n"
        "- After calling save_raw_data_to_json, STOP.\n"
    ),
    tools=[save_raw_data_to_json]
)
