from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext

from .json_writer_agent import persist_final_json
import json
import logging

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")

def exit_loop(tool_context: ToolContext):
    """
    Paranoid exit tool:
    - Ensures loop termination
    - Validates final JSON
    - Parses safely
    - Persists only if JSON is clean and complete
    - Logs every branch for traceability
    """

    logger.info("JSON approval detected. Terminating loop.")
    tool_context.actions.escalate = True

    # --- Extract LLM response safely ---
    raw = getattr(tool_context, "llm_response", None)

    if not raw:
        logger.error("No LLM response found in tool_context; cannot persist JSON.")
        return "Loop termination signaled, but no JSON persisted."

    # --- Attempt to parse JSON strictly ---
    parsed = None
    try:
        parsed = json.loads(raw)
        logger.info("Final LLM response successfully parsed as JSON.")
    except Exception as e:
        logger.error(f"Final LLM response is NOT valid JSON. Error: {e}")
        logger.debug(f"Raw content received:\n{raw}")
        return "Loop termination signaled, but JSON was invalid and not persisted."

    # --- Validate top-level structure ---
    if not isinstance(parsed, dict):
        logger.error("Parsed JSON is not an object; refusing to persist.")
        return "Loop termination signaled, but JSON structure invalid."

    required_keys = [
        "process_name",
        "industry_sector",
        "version",
        "introduction",
        "stakeholders",
        "process_steps",
        "tools_summary",
        "metrics",
        "reporting_and_analytics",
        "system_requirements",
        "appendix"
    ]

    missing = [k for k in required_keys if k not in parsed]

    if missing:
        logger.error(f"Final JSON missing required keys: {missing}")
        logger.debug(f"JSON content:\n{json.dumps(parsed, indent=2)}")
        return "Loop termination signaled, but JSON missing required fields."

    # --- Persist only if everything is clean ---
    try:
        persist_final_json(parsed)
        logger.info("Final JSON persisted successfully.")
    except Exception as e:
        logger.error(f"Failed to persist final JSON: {e}")
        return "Loop termination signaled, but persistence failed."

    return "Loop termination signaled and final JSON persisted."

# -----------------------------
# JSON NORMALIZER AGENT
# -----------------------------
json_normalizer_agent = LlmAgent(
    name="JSON_Normalizer_Agent",
    model="gemini-2.0-flash-001",
    include_contents="default",   # <-- REQUIRED so the agent sees the Reviewer output
    description="Normalizes arbitrary business process JSON into a stable enriched schema.",
    instruction=(
        "You are a JSON expert at normalization, formatting, and professional enrichment.\n\n"

        "=============================\n"
        "CONTROL LOGIC (CRITICAL)\n"
        "=============================\n"
        "You ALWAYS see the previous agent's message in the conversation history.\n"
        "Use ONLY the MOST RECENT previous message to determine your behavior.\n\n"

        "1. If the most recent previous message begins with 'JSON APPROVED':\n"
        "     - You MUST CALL the 'exit_loop' function immediately.\n"
        "     - Do NOT output any JSON or text.\n"
        "     - This is the ONLY way to stop the loop.\n\n"

        "2. If the most recent previous message begins with 'REVISION REQUIRED':\n"
        "     - Read the list of issues.\n"
        "     - Fix ONLY those issues.\n"
        "     - Produce a corrected JSON object.\n\n"

        "3. If there is no review message yet (first iteration):\n"
        "     - Produce the first normalized JSON object.\n\n"

        "=============================\n"
        "NORMALIZATION REQUIREMENTS\n"
        "=============================\n"
        "You MUST transform the input into this EXACT schema:\n"
        "{\n"
        "  \"process_name\": string,\n"
        "  \"industry_sector\": string,\n"
        "  \"version\": string,\n"
        "  \"introduction\": string,\n"
        "  \"stakeholders\": [ {\"responsibilities\": [string], \"role\": string, \"stakeholder_name\": string} ],\n"
        "  \"process_steps\": [\n"
        "      {\n"
        "        \"step_name\": string,\n"
        "        \"description\": string,\n"
        "        \"responsible_party\": string or list,\n"
        "        \"estimated_duration\": string,\n"
        "        \"deliverables\": [string],\n"
        "        \"dependencies\": [string],\n"
        "        \"success_criteria\": [string]\n"
        "      }\n"
        "  ],\n"
        "  \"tools_summary\": {},\n"
        "  \"metrics\": [ { \"name\": string, \"description\": string } ],\n"
        "  \"reporting_and_analytics\": {},\n"
        "  \"system_requirements\": [string],\n"
        "  \"appendix\": {}\n"
        "}\n\n"

        "=============================\n"
        "ENRICHMENT RULES\n"
        "=============================\n"
        "- Expand ALL descriptions and the introduction into multi‑sentence professional paragraphs.\n"
        "- NO bullet points inside description fields.\n"
        "- Flatten ANY nested structures (phases, sub_steps, dicts-as-steps) into a flat list.\n"
        "- Ensure all fields exist, even if empty.\n"
        "- Ensure all arrays contain only strings or objects as required.\n"
        "- Ensure all JSON is syntactically valid.\n\n"

        "=============================\n"
        "JSON OUTPUT CONTRACT\n"
        "=============================\n"
        "- When producing JSON, output ONLY the raw JSON object.\n"
        "- NO markdown.\n"
        "- NO ```json fences.\n"
        "- NO commentary.\n"
        "- MUST start with '{' and end with '}'.\n"
    ),
    tools=[exit_loop],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.4,
        top_p=1,
    ),
)
