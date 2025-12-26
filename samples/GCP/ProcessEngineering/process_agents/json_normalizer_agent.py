from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.tools.tool_context import ToolContext
from google.adk.agents.invocation_context import InvocationContext
from pydantic import BaseModel
import os, re, traceback, logging

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")

# --- Tool Definition ---
def exit_loop(tool_context: ToolContext):
    """Tool to exit the normalization loop when JSON is approved."""
    logger.info("JSON approved. Exiting normalization loop.")
    tool_context.actions.escalate = True
    return {}

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

        "OUTPUT CONTRACT (STRICT):\n"
        "- Output ONLY the raw JSON object.\n"
        "- Do NOT use markdown code blocks (e.g., no ```json).\n"
        "- Do NOT include natural language, intro text, or 'here is the updated JSON'.\n"
        "- Ensure the JSON is valid, complete, and contains no trailing commas.\n"
        "- Your response must start with '{' and end with '}'."

        "REVISION RULES:\n"
        "- If you receive feedback starting with 'REVISION REQUIRED', update the previous "
        "JSON object to address the specific critiques while maintaining all other enrichments.\n"
        "- If you receive feedback starting with 'JSON APPROVED', then STOP.\n"
    ),
    # tools=[exit_loop],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
)