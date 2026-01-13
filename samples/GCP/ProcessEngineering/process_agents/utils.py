# process_agents/utils.py
import os
import logging
import json
import glob

from typing import Any

logger = logging.getLogger("ProcessArchitect.Utils")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------
# INTERNAL HELPERS (NOT EXPOSED TO LLM)
# ---------------------------------------------------------------------

def _log_agent_activity(message: str):
    """Internal logging helper."""
    time.sleep(1.75 + random.random() * 0.75)
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
    time.sleep(1.75 + random.random() * 0.75)
    try:
        _log_agent_activity("Starting final JSON file persistence")
        result = _save_raw_data_to_json(json_content)
        _log_agent_activity(f"File persistence result: {result}")
        return result
    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"persist_final_json failed: {error_trace}")
        return "ERROR: persist_final_json encountered an unexpected failure."
    

# Tool to load the full process context (master + subprocesses)
# process_agents/utils.py

def load_full_process_context() -> str:
    """ Loads master process + subprocesses directly from disk. Never returns FATAL ERROR. Returns partial data if needed. """
    context = {
        "master_process": {},
        "subprocesses": [],
        "system_status": "PARTIAL"
    }
    master_path = os.path.join(PROJECT_ROOT, "output", "process_data.json")
    if os.path.exists(master_path):
        try:
            with open(master_path, "r", encoding="utf-8") as f:
                context["master_process"] = json.load(f)
                context["system_status"] = "OK"
        except Exception as e:
            context["system_status"] = f"ERROR: {e}"
    sub_dir = os.path.join(PROJECT_ROOT, "output", "subprocesses")
    if os.path.exists(sub_dir):
        for file_path in glob.glob(os.path.join(sub_dir, "*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    context["subprocesses"].append(json.load(f))
            except Exception as e:
                logger.error(f"Error loading {file_path}: {e}")
    return context

# Tool to load iteration feedback from output/iteration_feedback.json
def load_iteration_feedback() -> dict:
    """
    Loads feedback, metrics, and compliance violations from iteration_feedback.json.
    This is the 'Inbox' for the Design Agent to see what other agents have requested.
    """
    path = os.path.join(PROJECT_ROOT, "output", "iteration_feedback.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading feedback file: {e}")
    return {"status": "No feedback found", "issues": []}

def save_iteration_feedback(feedback_data: Any) -> str:
    """
    Saves feedback, metrics, or violations to iteration_feedback.json.
    Accepts Any type and handles conversion from string or dict to valid JSON.
    """
    try:
        os.makedirs("output", exist_ok=True)
        path = os.path.join(PROJECT_ROOT, "output", "iteration_feedback.json")
        
        # Artificial delay to prevent API burst issues in the loop
        time.sleep(1.75 + random.random() * 0.75)
        logger.info(f"Persisting iteration feedback of type {type(feedback_data)} to disk...")

        # Type Handling Logic
        if isinstance(feedback_data, dict):
            # Already a dict, use as-is
            final_content = feedback_data
        elif isinstance(feedback_data, str):
            # Attempt to parse if it's a JSON string, otherwise wrap it
            try:
                final_content = json.loads(feedback_data)
            except json.JSONDecodeError:
                logger.warning("Feedback input is a string but not valid JSON. Wrapping in issue object.")
                final_content = {"status": "REVISION REQUIRED", "raw_feedback": feedback_data}
        else:
            # Fallback for unexpected types (int, list, etc.)
            final_content = {"status": "REVISION REQUIRED", "data": str(feedback_data)}

        # Write to file
        with open(path, "w", encoding="utf-8") as f:
            json.dump(final_content, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Feedback successfully saved to {path}")
        return f"SUCCESS: Feedback persisted to {path}"

    except Exception as e:
        error_msg = f"ERROR: Failed to save feedback: {str(e)}"
        logger.error(error_msg)
        return error_msg
    
# Load the master process JSON from output/process_data.json
def load_master_process_json() -> dict:
    """
    Loads and returns the contents of output/process_data.json as a Python dict.
    Returns an empty dict if the file does not exist or cannot be loaded.
    """
    path = os.path.join(PROJECT_ROOT, "output", "process_data.json")
    if not os.path.exists(path):
        logger.warning(f"{path} does not exist.")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        return {}

# Load instruction from a file in the instructions directory
def load_instruction(filename: str) -> str:
    logger.info(f"Loading instruction from {filename}")
    try:
        instruction_path = os.path.join(PROJECT_ROOT, "instructions", filename)
        with open(instruction_path, "r", encoding="utf-8") as f:
            instruction = f.read()
            logger.debug(f"Instruction content: {instruction[:100]}...")  # Log first 100 chars
            return instruction
    except FileNotFoundError:
        logger.error(f"Instruction file {filename} not found.")
        raise
    except Exception as e:
        logger.error(f"Error loading instruction file {filename}: {e}")
        raise

# Validate that all required instruction files exist and are readable
def validate_instruction_files():
    """
    Validates that all instruction files exist and are readable.
    Logs a single consolidated error if any are missing.
    """
    instruction_dir = os.path.join(PROJECT_ROOT, "instructions")

    required_files = [
        "agent.txt",
        "analysis_agent.txt",
        "compliance_agent.txt",
        "consultant_agent.txt",
        "design_agent.txt",
        "doc_generation_agent.txt",
        "edge_inference_agent.txt",
        "json_normalizer_agent.txt",
        "json_review_agent.txt",
        "json_writer_agent.txt",
        "scenario_tester_agent.txt",
        "simulation_agent.txt",
        "subprocess_generator_agent.txt",
        "update_analysis_agent.txt"
    ]

    missing = []
    unreadable = []

    for filename in required_files:
        path = os.path.join(instruction_dir, filename)
        if not os.path.exists(path):
            missing.append(filename)
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                _ = f.read(50)  # sanity check
        except Exception as e:
            unreadable.append((filename, str(e)))

    if missing or unreadable:
        logger.error("Instruction file validation failed.")
        if missing:
            logger.error(f"Missing: {missing}")
        if unreadable:
            logger.error(f"Unreadable: {unreadable}")
        return False
    else:
        logger.info("All instruction files validated successfully.")
        return True
