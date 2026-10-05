"""Per-step subprocess expansion: load the parent process's steps, persist
a generated subprocess flow for one of them.

Ported from the ADK sample's SubprocessDriverAgent/SubprocessWriterAgent
(subprocess_driver_agent.py, subprocess_writer_agent.py). Simplified from
two agents (a generator + a separate writer handing data between them via
ADK session state) into one: here, the generator's own tool-call arguments
already carry the validated data directly, so there's no session-state hop
needed -- this save function does the writer's persistence+security job in
one step.
"""

import json
import os
from typing import Any, Dict, List

from coded_tools.common import paths
from coded_tools.common.filenames import safe_filename_component
from coded_tools.common.process_json import load_master_process_json


def _subprocess_dir() -> str:
    # Reads paths.OUTPUT_DIR off the module (not a name copied in via
    # "from ... import OUTPUT_DIR", which would freeze a stale value at
    # import time) so tests can isolate it via monkeypatch -- see
    # coded_tools/common/paths.py's own output_path for the same reasoning.
    return os.path.join(paths.OUTPUT_DIR, "subprocesses")


def load_process_steps() -> List[Dict[str, Any]]:
    data = load_master_process_json()
    steps = data.get("process_steps", [])
    return steps if isinstance(steps, list) else []


def save_subprocess_flow(step_name: str, flow: Dict[str, Any]) -> Dict[str, Any]:
    subprocess_dir = _subprocess_dir()
    os.makedirs(subprocess_dir, exist_ok=True)

    safe_name = safe_filename_component(step_name)
    file_path = os.path.join(subprocess_dir, f"{safe_name}.json")

    resolved_dir = os.path.realpath(subprocess_dir)
    resolved_path = os.path.realpath(file_path)
    if os.path.commonpath([resolved_dir, resolved_path]) != resolved_dir:
        return {
            "status": "ERROR",
            "error": f"Refusing to write outside {subprocess_dir}: step_name={step_name!r} resolved to {resolved_path!r}",
        }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(flow, f, indent=2)
        return {"status": "OK", "path": file_path}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
