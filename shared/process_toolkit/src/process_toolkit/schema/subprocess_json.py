"""Per-step subprocess expansion: load the parent process's steps, persist
a generated subprocess flow for one of them.
"""

import json
import os
from typing import Any, Dict, List

from process_toolkit import paths
from process_toolkit.filenames import safe_filename_component
from process_toolkit.schema.process_json import load_master_process_json


def load_process_steps() -> List[Dict[str, Any]]:
    data = load_master_process_json()
    steps = data.get("process_steps", [])
    return steps if isinstance(steps, list) else []


def save_subprocess_flow(step_name: str, flow: Dict[str, Any]) -> Dict[str, Any]:
    subprocess_dir = paths.output_dir("subprocesses")

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
