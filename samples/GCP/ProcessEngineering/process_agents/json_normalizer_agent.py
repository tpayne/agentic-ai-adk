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
    """
    Terminates the normalization loop and persists the final validated JSON.
    Includes robust extraction to handle trailing 'extra data' from the LLM.
    """
    time.sleep(1.75 + random.random() * 0.75)
    logger.info("JSON approval detected. Terminating loop.")
    tool_context.actions.escalate = True

    candidate = None

    try:
        # Retrieve the most recent LLM response which should contain the approved JSON
        candidate = tool_context.state.get('approved_json')
        if candidate is None:
            logger.error("No LLM response found in tool_context; cannot persist JSON. Ignored")
            return "Loop termination signaled, but no JSON persisted."
        
        # Robust extraction: find the first '{' and the LAST '}' to strip preamble or trailing chatter
        if isinstance(candidate, str):
            start_index = candidate.find('{')
            end_index = candidate.rfind('}')
            
            if start_index != -1 and end_index != -1 and end_index > start_index:
                candidate = candidate[start_index:end_index + 1]
            else:
                logger.error("Could not find valid JSON boundaries in the response.")
                return "Loop termination signaled, but JSON structure invalid."
                
        logger.debug(f"LLM response to be persisted (extracted): {str(candidate)[:100]}...")
    except Exception as e:
        logger.error(f"Error retrieving 'approved_json' from tool_context: {e}")
        return "Loop termination signaled, but no JSON persisted."

    # Convert the string candidate into a Python dictionary
    if isinstance(candidate, str):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as e:
            logger.error(f"Final LLM response is NOT valid JSON. Error: {e}")
            logger.debug(f"Raw content received:\n{candidate}")
            return "Loop termination signaled, but JSON structure invalid."
    else:
        parsed = candidate

    # Validate that all required top-level keys are present
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
        return "Loop termination signaled, but JSON missing required fields."

    # Save the cleaned JSON to output/process_data.json
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
        temperature=0.1,
        top_p=1,
        max_output_tokens=8192,
    ),
    output_key="approved_json",
)