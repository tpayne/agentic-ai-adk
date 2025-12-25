from google.adk.agents import LlmAgent
from google.genai import types
from pydantic import BaseModel
import os, re, traceback, logging

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")


def log_agent_activity(message: str):
    logger.info(f"--- [DIAGNOSTIC] JSON_Normalizer: {message} ---")
    return "Log recorded."


def save_raw_data_to_json(json_content: str) -> str:
    """Save the JSON to output/process_data.json."""
    try:
        logger.info("Saving normalized JSON to file...")
        os.makedirs("output", exist_ok=True)

        clean_json = re.sub(r'^```json\s*|```$', "", json_content.strip(), flags=re.MULTILINE)

        path = "output/process_data.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(clean_json)
            f.flush()

        return path

    except Exception:
        traceback.print_exc()
        return "ERROR: Failed to save JSON"


# -----------------------------
# JSON NORMALIZER AGENT
# -----------------------------
json_normalizer_agent = LlmAgent(
    name="JSON_Normalizer_Agent",
    model="gemini-2.0-flash-001",
    description="Normalizes arbitrary business process JSON into a stable enriched schema.",
    instruction=(
        "You are a Senior Process Architect.\n\n"
        
        "Your task is to normalize and enrich business process JSON according to a defined schema.\n\n"

        "You operate in four strict steps:\n\n"

        "STEP 1: LOGGING\n"
        "Immediately CALL the tool log_agent_activity('Starting Enrichment and Schema Mapping').\n\n"

        "STEP 2: ENRICHMENT & MAPPING\n"
        "- Transform the input data into the following schema. You MUST expand every 'description' "
        "and the 'introduction' into detailed paragraphs (Enrichment).\n"
        "{\n"
        "  \"process_name\": string, \"version\": string, \"introduction\": string,\n"
        "  \"stakeholders\": [], \"process_steps\": [], \"tools_summary\": {},\n"
        "  \"metrics\": [], \"reporting_and_analytics\": {}, \n"
        "  \"system_requirements\": [], \"appendix\": {}\n"
        "}\n\n"

        "STEP 3: REVISION RULE FOR THE REVIEW PROCESS:\n"
        "- If you receive feedback beginning with 'REVISION REQUIRED', you MUST update your "
        "  previous JSON to address those comments.\n"
        "- The updated output MUST again be a single, complete JSON object.\n\n"

        "STEP 4: FINAL SEXECUTION\n"
        "- Lastly, CALL the tool 'save_raw_data_to_json' with the resulting JSON object.\n"
    ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
    tools=[save_raw_data_to_json, log_agent_activity]
)