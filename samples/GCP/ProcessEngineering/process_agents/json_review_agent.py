# process_agents/json_review_agent.py
from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext

from .json_writer_agent import persist_final_json
from .utils import load_instruction

import json
import logging

logger = logging.getLogger("ProcessArchitect.JsonReview")

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
        logger.error(f"Failed to persist final JSON: {e}. Ignored")
        return "Loop termination signaled, but persistence failed."

    return "Loop termination signaled and final JSON persisted."


# -----------------------------
# JSON REVIEW AGENT
# -----------------------------
json_review_agent = LlmAgent(
    name='Json_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Review JSON for validity, compliance, and best practices.',
    include_contents="default",
    tools=[exit_loop],
    instruction=load_instruction("json_review_agent.txt"),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
)
