from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext

from .json_writer_agent import persist_final_json
from .utils import load_instruction

import json
import logging
from typing import Any

import time
import random 

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")

def exit_loop(tool_context: ToolContext):
    time.sleep(0.75 + random.random() * 0.75)
    logger.info("JSON approval detected. Terminating loop.")
    tool_context.actions.escalate = True

    candidate = None

    try:
        candidate = tool_context.state['approved_json']
        if candidate is None:
            logger.error("No LLM response found in tool_context; cannot persist JSON. Ignored")
            return "Loop termination signaled, but no JSON persisted."
        else:
            start_index = candidate.find('{')
            if start_index != -1:
                candidate = candidate[start_index:]
        logger.debug(f"LLM response to be persisted: {str(candidate)[:100]}...")  # log first 100 chars
    except Exception as e:
        logger.error(f"Error retrieving 'approved_json' from tool_context: {e}")
        return "Loop termination signaled, but no JSON persisted."

    # If candidate is already parsed JSON (dict/list), use it directly
    if isinstance(candidate, (dict, list)):
        parsed = candidate
    else:
        # candidate is likely a string; try strict parse
        try:
            parsed = json.loads(candidate)
            logger.info("Final LLM response successfully parsed as JSON.")
        except Exception as e:
            logger.error(f"Final LLM response is NOT valid JSON. Error: {e}")
            logger.info(f"Raw content received:\n{candidate[:100]}")  # log first 100 chars
            return "Loop termination signaled, but JSON was invalid and not persisted."

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

    try:
        persist_final_json(parsed)
        logger.info("Final JSON persisted successfully.")
    except Exception as e:
        logger.error(f"Failed to persist final JSON: {e}. Ignored")
        return "Loop termination signaled, but persistence failed."

    return "Loop termination signaled and final JSON persisted."

# -----------------------------
# JSON NORMALIZER AGENT
# -----------------------------
json_normalizer_agent = LlmAgent(
    name="JSON_Normalizer_Agent",
    model="gemini-2.0-flash-001",
    tools=[exit_loop],
    include_contents="default",
    description="Normalizes arbitrary business process JSON into a stable enriched schema.",
    instruction=load_instruction("json_normalizer_agent.txt"),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.4,
        top_p=1,
    ),
    output_key="approved_json",
)