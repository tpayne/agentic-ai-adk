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
    if not isinstance(steps, list):
        return []
    # When no real baseline exists yet, load_master_process_json falls back
    # to PROCESS_TEMPLATE, whose process_steps entry is a one-item
    # structural placeholder (step_name="") rather than []  -- same
    # one-item-hint shape every other template field uses, so Design_Agent
    # has something to normalize against. That placeholder is never a real
    # step to expand into a subprocess, so it's filtered out here rather
    # than special-cased at every caller.
    return [s for s in steps if isinstance(s, dict) and s.get("step_name")]


def validate_subprocess_flow(flow: Dict[str, Any]) -> Dict[str, Any]:
    """Checked before every save -- a sub-step missing substep_name/description
    doesn't fail loudly anywhere else: the document renderer silently falls
    back to a generic "Sub-step N" heading and a templated one-line
    description instead of raising, so a generation that drops these fields
    (observed from the model despite the generator agent's own instructions
    listing them as required) would otherwise only surface as a
    suspiciously thin document, long after this tool call succeeded."""
    issues: List[Dict[str, str]] = []

    sub_steps = flow.get("subprocess_flow")
    if not isinstance(sub_steps, list) or not sub_steps:
        issues.append({"location": "subprocess_flow", "issue": "subprocess_flow must be a non-empty list"})
        return {"valid": False, "issues": issues}

    for i, sub in enumerate(sub_steps):
        loc = f"subprocess_flow[{i}]"
        if not isinstance(sub, dict):
            issues.append({"location": loc, "issue": "Each sub-step must be an object"})
            continue
        if not sub.get("substep_name"):
            issues.append({"location": f"{loc}.substep_name", "issue": "substep_name is required"})
        if not sub.get("description"):
            issues.append({"location": f"{loc}.description", "issue": "description is required"})

    return {"valid": not issues, "issues": issues}


def save_subprocess_flow(step_name: str, flow: Dict[str, Any]) -> Dict[str, Any]:
    validation = validate_subprocess_flow(flow)
    if not validation["valid"]:
        return {"status": "ERROR", "error": "Invalid subprocess_flow.", "issues": validation["issues"]}

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
