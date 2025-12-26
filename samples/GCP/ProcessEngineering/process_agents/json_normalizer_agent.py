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
        "You are a JSON expert at normalization, formatting, and professional enrichment.\n\n"

        "TASK:\n"
        "1. Normalize and enrich business process data into the stable schema provided below.\n"
        "2. ENRICHMENT RULE: You MUST expand every 'description' and the 'introduction' into "
        "detailed, professional paragraphs. Do not use bullet points for these fields.\n"
        "3. Transform the input into this EXACT schema:\n"
        "{\n"
        "  \"process_name\": string,\n"
        "  \"version\": string,\n"
        "  \"introduction\": string,\n"
        "  \"stakeholders\": [],\n"
        "  \"process_steps\": [],\n"
        "  \"tools_summary\": {},\n"
        "  \"metrics\": [],\n"
        "  \"reporting_and_analytics\": {},\n"
        "  \"system_requirements\": [],\n"
        "  \"appendix\": {}\n"
        "}\n\n"

        "REVISION & LOOPING RULES:\n"
        "- If you receive feedback starting with 'REVISION REQUIRED', update the previous "
        "JSON object to address the specific critiques while maintaining all other enrichments.\n"
        "- If you see 'JSON APPROVED' in the conversation history, your task is complete; "
        "however, if prompted to generate, always output the full, final JSON.\n\n"

        "OUTPUT CONTRACT (STRICT):\n"
        "- Output ONLY the raw JSON object.\n"
        "- Do NOT use markdown code blocks (e.g., no ```json).\n"
        "- Do NOT include natural language, intro text, or 'here is the updated JSON'.\n"
        "- Ensure the JSON is valid, complete, and contains no trailing commas.\n"
        "- Your response must start with '{' and end with '}'."
    ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
)