# process_agents/json_writer_agent.py

import os
import re
import json
import logging
import traceback

from google.adk.agents import LlmAgent
from google.genai import types

logger = logging.getLogger("ProcessArchitect.JsonWriter")

# ---------------------------------------------------------------------
# TOOLS
# ---------------------------------------------------------------------

def log_agent_activity(message: str):
    """Internal tool to log agent progress for debugging."""
    logger.info(f"--- [DIAGNOSTIC] JSON_Writer: {message} ---")
    return "Log recorded."


def save_raw_data_to_json(json_content) -> str:
    """
    Saves the finalized JSON to output/process_data.json.
    Includes robust repair logic for large/truncated LLM payloads.
    """
    try:
        logger.info("Saving normalized JSON to file...")
        os.makedirs("output", exist_ok=True)
        path = "output/process_data.json"

        # 1. Normalize input to string
        if isinstance(json_content, dict):
            raw_str = json.dumps(json_content)
        else:
            raw_str = str(json_content).strip()

        # 2. Extract JSON from potential "JSON APPROVED" or Markdown wrapper
        # We look for the first '{' and the last '}'
        start_index = raw_str.find('{')
        end_index = raw_str.rfind('}')
        
        if start_index != -1 and end_index != -1:
            raw_str = raw_str[start_index:end_index+1]
        
        # 3. Strip Markdown Fences just in case
        raw_str = re.sub(r'^```json\s*|```$', "", raw_str, flags=re.MULTILINE)

        # 4. Attempt Validation and Repair
        try:
            parsed = json.loads(raw_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Standard JSON decode failed at char {e.pos}. Attempting structural repair...")
            
            try:
                # IMPORTANT: Module name is json_repair, package is json-repair
                from json_repair import repair_json
                repaired_str = repair_json(raw_str)
                parsed = json.loads(repaired_str)
                logger.info("JSON successfully repaired and loaded.")
            except ImportError:
                logger.error("json-repair library not found. Install via 'pip install json-repair'")
                return f"ERROR: JSONDecodeError at {e.pos} and json-repair is not installed."
            except Exception as repair_err:
                logger.error(f"Repair failed: {str(repair_err)}")
                return "ERROR: Critical structural failure in JSON payload."

        # 5. Final Write
        clean_json = json.dumps(parsed, indent=2, ensure_ascii=False)
        with open(path, "w", encoding="utf-8") as f:
            f.write(clean_json)
            f.flush()

        logger.info(f"Successfully saved JSON to {path}")
        return path

    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"Failed to save JSON: {error_trace}")
        return "ERROR: Failed to save JSON"

# ---------------------------------------------------------------------
# AGENT DEFINITION
# ---------------------------------------------------------------------

json_writer_agent = LlmAgent(
    name="JSON_Writer_Agent",
    model="gemini-2.0-flash-001",
    description="Final persistence agent that writes approved JSON to the file system.",
    instruction=(
        "You are a JSON Writing Expert. Your task is to save the finalized business "
        "process data to a physical file.\n\n"

        "You will strictly follow these three steps to operate:\n\n"

        "STEP 1: LOGGING\n"
        "Immediately CALL the tool 'log_agent_activity' with the message: 'Starting final JSON file persistence'.\n\n"

        "STEP 2: DATA EXTRACTION\n"
        "- You will receive input from the Reviewer agent containing a JSON object.\n"
        "- Extract that JSON object.\n"
        "- Ensure the JSON is complete.\n\n"

        "STEP 3: FILE WRITING\n"
        "- You MUST CALL the 'save_raw_data_to_json' tool with the JSON object.\n"
        "- This tool will handle all validation and repair logic.\n"
        "- Await the tool's response which will confirm the file path or report errors.\n\n"

        "CRITICAL RULES:\n"
        "- You MUST use the provided tools for logging and file writing.\n"
        "- Do NOT attempt to write files directly.\n"
        "- Do NOT output any text other than the tool calls and their results.\n"
    ),
    tools=[save_raw_data_to_json, log_agent_activity]
)