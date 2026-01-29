# process_agents/utils.py
import os
import json
import glob
import time
import random
import re
import traceback
import logging
import configparser
from typing import Any, Union

logger = logging.getLogger("ProcessArchitect.Utils")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Internal cache
_CACHE: Union[configparser.ConfigParser, None] = None
PROPERTIES_FILE = os.path.join(PROJECT_ROOT, 'properties', 'agentapp.properties')

def getProperty(prop: str, section: str = 'SETTINGS',
                default: Union[str, int, float, bool, None] = None) -> Any:
    global _CACHE
    if _CACHE is None:
        # One-time disk read with error handling for path
        config = configparser.ConfigParser()
        if os.path.exists(PROPERTIES_FILE):
            config.read(PROPERTIES_FILE)
        _CACHE = config

    try:
        val = _CACHE.get(section, prop)
    except (configparser.NoOptionError, configparser.NoSectionError):
        # Fallback to environment variable
        env_val = os.getenv(prop)
        if env_val is not None:
            val = env_val
        else:
            return default

    # Clean up quotes (e.g., "5" -> 5)
    val = val.strip('"').strip("'")

    # Boolean conversion
    val_lower = val.lower()
    if val_lower in ['true', 'yes', 'on']:
        return True
    if val_lower in ['false', 'no', 'off']:
        return False

    # Integer conversion
    try:
        return int(val)
    except ValueError:
        pass

    # Float conversion
    try:
        return float(val)
    except ValueError:
        pass

    # Default: string (or default if empty)
    return val if val != '' else default

# ---------------------------------------------------------------------
# INTERNAL HELPERS (NOT EXPOSED TO LLM)
# ---------------------------------------------------------------------

def _safe_sleep_from_property(name: str, default: float = 0.25):
    pv = getProperty(name, default=default)
    try:
        base = float(pv)
    except Exception:
        base = default
    time.sleep(base + random.random() * 0.75)

def _log_agent_activity(message: str):
    """Internal logging helper."""
    _safe_sleep_from_property("modelSleep", default=0.25)
    logger.debug(f"--- [DIAGNOSTIC] Utils: {message} ---")

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

def _validate_process_json(data: dict):
    if not isinstance(data, dict):
        logger.error("Process JSON does not contain a JSON object.")
        return None

    required_top_keys = [
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
        "assumptions",
        "constraints",
        "appendix",
        "critical_success_factors",
        "critical_failure_factors",
    ]

    for key in required_top_keys:
        if key not in data:
            logger.error(f"Missing required top-level key '{key}'.")
            return None

    if not isinstance(data.get("process_name"), str) or not data["process_name"].strip():
        logger.error("Invalid or empty 'process_name' in process JSON.")
        return None

    if not isinstance(data.get("process_steps"), list) or len(data["process_steps"]) == 0:
        logger.error("Invalid or empty 'process_steps' in process JSON.")
        return None

    required_step_keys = [
        "step_name",
        "description",
        "responsible_party",
        "estimated_duration",
        "deliverables",
        "inputs",
        "outputs",
        "dependencies",
        "success_criteria"
    ]

    for idx, step in enumerate(data["process_steps"]):
        if not isinstance(step, dict):
            logger.error(f"process_steps[{idx}] is not an object.")
            return None

        for sk in required_step_keys:
            if sk not in step:
                logger.error(f"Missing key '{sk}' in process_steps[{idx}].")
                return None

    return data

def _save_raw_data_to_json(json_content) -> str:
    """
    Saves the finalized JSON to output/process_data.json.
    Includes robust repair logic for large/truncated LLM payloads.
    Uses a lock file to prevent race conditions with concurrent reads/writes.

    This is internal. The only exposed tool is persist_final_json.
    """
    output_dir = os.path.join(PROJECT_ROOT, "output")
    path = os.path.join(output_dir, "process_data.json")
    lock_path = os.path.join(output_dir, ".process_data.lock")

    def acquire_lock(timeout: float = 5.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if not os.path.exists(lock_path):
                try:
                    with open(lock_path, "w", encoding="utf-8") as lf:
                        lf.write(str(os.getpid()))
                    return True
                except Exception as e:
                    logger.error(f"Failed to create lock file: {e}")
            time.sleep(0.1)
        logger.error("Timeout acquiring process_data lock.")
        return False

    def release_lock():
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception as e:
            logger.error(f"Failed to remove lock file: {e}")

    try:
        _log_agent_activity("Saving normalized JSON to file...")
        os.makedirs(output_dir, exist_ok=True)

        # Acquire lock before writing
        if not acquire_lock():
            return "ERROR: Could not acquire lock for JSON persistence."

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
            raw_path = os.path.join(output_dir, "process_data_raw.json")
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
                logger.debug("JSON successfully repaired and loaded.")
            except ImportError:
                logger.error(
                    "json-repair library not found. "
                    "Install via 'pip install json-repair'. "
                )
                raw_path = os.path.join(output_dir, "process_data_raw.json")
                with open(raw_path, "w", encoding="utf-8") as rf:
                    rf.write(raw_str)
                return (
                    f"ERROR: JSONDecodeError at {e.pos} and json-repair is not installed. "
                    f"Raw JSON written to {raw_path}."
                )
            except Exception as repair_err:
                logger.error(
                    f"Repair failed: {str(repair_err)}. "
                )
                raw_path = os.path.join(output_dir, "process_data_raw.json")
                with open(raw_path, "w", encoding="utf-8") as rf:
                    rf.write(raw_str)
                return (
                    "ERROR: Critical structural failure in JSON payload. "
                    f"Raw JSON written to {raw_path}."
                )

        if parsed is None:
            logger.error("Parsed JSON is None after validation/repair. ")
            raw_path = os.path.join(output_dir, "process_data_raw.json")
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_str)
            return (
                "ERROR: Unable to obtain valid JSON. "
                f"Raw JSON written to {raw_path}."
            )

        if _validate_process_json(parsed) is None:
            logger.error("Parsed JSON is invalid. ")
            raw_path = os.path.join(output_dir, "process_data_raw.json")
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_str)
            return (
                "ERROR: The JSON to persist was not valid. "
                f"Raw JSON written to {raw_path}."
            )

        # 5. Final write of clean, repaired JSON
        clean_json = json.dumps(parsed, indent=2, ensure_ascii=False)

        # Skip write if identical
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as existing:
                    old = json.load(existing)
                if _json_equal(old, parsed):
                    _log_agent_activity(
                        f"No changes detected; skipping write to {path}."
                    )
                    return path
            except Exception:
                pass  # If comparison fails, fall through to write

        with open(path, "w", encoding="utf-8") as f:
            f.write(clean_json)

        _log_agent_activity(
            f"Successfully saved JSON to {path} "
            f"({'repaired' if used_repair else 'clean'})."
        )
        return path

    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"Failed to save JSON: {error_trace}")
        return "ERROR: Failed to save JSON"

    finally:
        release_lock()

def _json_equal(a: dict, b: dict) -> bool:
    """Return True if two JSON objects are semantically identical."""
    try:
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    except Exception:
        return False

# ---------------------------------------------------------------------
# EXPOSED TOOL (SINGLE ENTRYPOINT FOR LLM)
# ---------------------------------------------------------------------

def persist_final_json(json_content) -> str:
    """
    Public tool for the LLM:
    - Logs that final persistence is starting.
    - Calls the internal saver with the provided JSON content.
    - Returns the final path or error message.
    """
    _safe_sleep_from_property("modelSleep", default=0.25)

    try:
        _log_agent_activity("Starting final JSON file persistence")
        result = _save_raw_data_to_json(json_content)

        if isinstance(result, str) and "No changes detected" not in result:
            _log_agent_activity(f"File persistence result: {result}")

        return result

    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"persist_final_json failed: {error_trace}")
        return "ERROR: persist_final_json encountered an unexpected failure."

# Tool to load the full process context (master + subprocesses)
def load_full_process_context() -> dict:
    """Loads master process + subprocesses directly from disk. Never returns FATAL ERROR. Returns partial data if needed."""
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
    _log_agent_activity("Loading iteration feedback from disk...")
    _safe_sleep_from_property("modelSleep", default=0.25)

    path = os.path.join(PROJECT_ROOT, "output", "iteration_feedback.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading feedback file: {e}")

    return {"status": "No feedback found", "issues": []}

def save_iteration_feedback(feedback_data: Any):
    """
    Saves iteration feedback to disk. 
    Ensures that the 'data' field is saved as a clean JSON list/object, 
    not a stringified representation.
    """
    _log_agent_activity(f"Persisting iteration feedback of type {type(feedback_data)} to disk...")
    _safe_sleep_from_property("modelSleep", default=0.25)

    output_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "iteration_feedback.json")

    # Artificial delay to prevent API burst issues in the loop
    _safe_sleep_from_property("modelSleep", default=0.25)

    # 1. Clean the incoming data
    processed_data = feedback_data
    if isinstance(feedback_data, str):
        try:
            # Normalize common LLM output issues (single quotes)
            normalized_str = feedback_data.replace("'", '"')
            processed_data = json.loads(normalized_str)
        except Exception:
            # If parsing fails, treat it as a raw comment string
            processed_data = feedback_data

    # Determine status based on presence of feedback or approval markers
    status = "REVISION REQUIRED"
    if not processed_data or (isinstance(processed_data, dict) and processed_data.get("status") == "JSON APPROVED"):
        status = "JSON APPROVED"

    payload = {
        "status": status,
        "data": processed_data  # Saved as a clean JSON structure
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        logger.debug(f"--- [DIAGNOSTIC] Utils: Feedback successfully saved to disk  ---")
        return f"SUCCESS: Feedback persisted to {path}"
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        return f"ERROR: Could not save feedback: {str(e)}"

# Load the master process JSON from output/process_data.json
def load_master_process_json() -> Union[dict, None]:
    """
    Loads and returns the contents of output/process_data.json as a Python dict.

    Returns:
      - A valid dict if the file exists AND contains a structurally valid process JSON.
      - None if the file is missing, unreadable, empty, locked, or missing required schema keys.
    """

    path = os.path.join(PROJECT_ROOT, "output", "process_data.json")
    lock_path = os.path.join(PROJECT_ROOT, "output", ".process_data.lock")

    # Wait for lock to clear (writer in progress)
    start = time.time()
    while os.path.exists(lock_path):
        if time.time() - start > 5.0:
            logger.error("Timeout waiting for lock release in load_master_process_json.")
            return None
        time.sleep(0.1)

    # File existence
    if not os.path.exists(path):
        logger.warning(f"{path} does not exist.")
        return None

    try:
        # Read file content
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()

        if not raw:
            logger.error(f"{path} is empty on disk.")
            return None

        # Parse JSON
        try:
            data = json.loads(raw)
        except Exception as e:
            logger.error(f"Failed to parse JSON in {path}: {e}")
            return None

        # Validate using your existing validator
        validated = _validate_process_json(data)
        if validated is None:
            logger.error(f"Validation failed for {path}.")
            return None

        return validated

    except Exception as e:
        logger.error(f"Unexpected error loading {path}: {e}")
        return None

# Load instruction from a file in the instructions directory
def load_instruction(filename: str) -> str:
    _log_agent_activity(f"Loading instruction from {filename}")
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
def validate_instruction_files() -> bool:
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
        _log_agent_activity("All instruction files validated successfully.")
        return True