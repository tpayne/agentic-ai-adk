# process_agents/json_writer_agent.py

import os
import re
import json
import logging
import traceback

from google.adk.agents import LlmAgent
from google.genai import types

from .utils import load_instruction

import time
import random  

logger = logging.getLogger("ProcessArchitect.JsonWriter")


# ---------------------------------------------------------------------
# INTERNAL HELPERS (NOT EXPOSED TO LLM)
# ---------------------------------------------------------------------

def _log_agent_activity(message: str):
    """Internal logging helper."""
    time.sleep(1.25 + random.random() * 0.75)
    logger.info(f"--- [DIAGNOSTIC] JSON_Writer: {message} ---")


def _extract_json_brace_balanced(text: str) -> str:
    """
    Extract the FIRST valid JSON object from a text blob using brace counting.
    Handles reviewer prefixes like 'JSON APPROVED' or 'REVISION REQUIRED'.
    """
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in text")

    brace_count = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                return text[start:i+1]

    raise ValueError("JSON braces not balanced")


def _save_raw_data_to_json(json_content) -> str:
    """
    Saves the finalized JSON to output/process_data.json.
    Includes robust repair logic for large/truncated LLM payloads.

    This is internal. The only exposed tool is persist_final_json.
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

        # 2. Extract JSON using brace-balanced logic
        try:
            raw_str = _extract_json_brace_balanced(raw_str)
        except Exception as e:
            logger.error(f"Failed to extract JSON object: {e}")
            raw_path = "output/process_data_raw.json"
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_str)
            return (
                f"ERROR: Could not extract JSON object. Raw content saved to {raw_path}."
            )

        # 3. Strip Markdown fences
        raw_str = re.sub(r'^```json\s*|```$', "", raw_str, flags=re.MULTILINE)

        # 4. Attempt validation and repair
        parsed = None
        used_repair = False
        try:
            parsed = json.loads(raw_str)
        except json.JSONDecodeError as e:
            logger.warning(
                f"Standard JSON decode failed at char {e.pos}. "
                f"Attempting structural repair..."
            )
            try:
                from json_repair import repair_json
                repaired_str = repair_json(raw_str)
                parsed = json.loads(repaired_str)
                used_repair = True
                logger.info("JSON successfully repaired and loaded.")
            except ImportError:
                logger.error(
                    "json-repair library not found. "
                    "Install via 'pip install json-repair'. "
                    "Writing raw JSON to output/process_data_raw.json for inspection."
                )
                raw_path = "output/process_data_raw.json"
                with open(raw_path, "w", encoding="utf-8") as rf:
                    rf.write(raw_str)
                return (
                    f"ERROR: JSONDecodeError at {e.pos} and json-repair is not installed. "
                    f"Raw JSON written to {raw_path}."
                )
            except Exception as repair_err:
                logger.error(
                    f"Repair failed: {str(repair_err)}. "
                    "Writing raw JSON to output/process_data_raw.json for inspection."
                )
                raw_path = "output/process_data_raw.json"
                with open(raw_path, "w", encoding="utf-8") as rf:
                    rf.write(raw_str)
                return (
                    "ERROR: Critical structural failure in JSON payload. "
                    f"Raw JSON written to {raw_path}."
                )

        if parsed is None:
            logger.error(
                "Parsed JSON is None after validation/repair. "
                "Writing raw JSON to output/process_data_raw.json for inspection."
            )
            raw_path = "output/process_data_raw.json"
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_str)
            return (
                "ERROR: Unable to obtain valid JSON. "
                f"Raw JSON written to {raw_path}."
            )

        # 5. Final write of clean, repaired JSON
        clean_json = json.dumps(parsed, indent=2, ensure_ascii=False)
        with open(path, "w", encoding="utf-8") as f:
            f.write(clean_json)

        logger.info(
            f"Successfully saved JSON to {path} "
            f"({'repaired' if used_repair else 'clean'})."
        )
        return path

    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"Failed to save JSON: {error_trace}")
        return "ERROR: Failed to save JSON"


# ---------------------------------------------------------------------
# EXPOSED TOOL (SINGLE ENTRYPOINT FOR LLM)
# ---------------------------------------------------------------------

def persist_final_json(json_content) -> str:
    """
    Public tool for the LLM:

    - Logs that final persistence is starting.
    - Calls the internal saver with the provided JSON content.
    - Returns the final path or error message.

    This is the ONLY tool the agent needs to call.
    """
    time.sleep(1.25 + random.random() * 0.75)
    try:
        _log_agent_activity("Starting final JSON file persistence")
        result = _save_raw_data_to_json(json_content)
        _log_agent_activity(f"File persistence result: {result}")
        return result
    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"persist_final_json failed: {error_trace}")
        return "ERROR: persist_final_json encountered an unexpected failure."
    
# ---------------------------------------------------------------------
# AGENT DEFINITION (SINGLE TOOL, ATOMIC BEHAVIOR)
# ---------------------------------------------------------------------

json_writer_agent = LlmAgent(
    name="JSON_Writer_Agent",
    model="gemini-2.0-flash-001",
    description="Final persistence agent that writes approved JSON to the file system.",
    instruction=load_instruction("json_writer_agent.txt"),
    tools=[persist_final_json],  # Use the exposed tool only
)
