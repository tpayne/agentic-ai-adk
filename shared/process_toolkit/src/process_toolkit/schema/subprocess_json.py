"""Per-step subprocess expansion: load the parent process's steps, persist
a generated subprocess flow for one of them.
"""

import json
import logging
import os
from typing import Any, Dict, List

from process_toolkit import paths
from process_toolkit.filenames import safe_filename_component
from process_toolkit.schema.process_json import load_master_process_json

logger = logging.getLogger("ProcessArchitect.SubprocessJson")


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
    real_steps = [s for s in steps if isinstance(s, dict) and s.get("step_name")]
    logger.debug("load_process_steps: %d real step(s) found.", len(real_steps))
    return real_steps


# Below this, a sub-step description is a bare clause, not the multi-
# sentence paragraph the document needs -- calibrated well below a real,
# human-reviewed reference document's own shortest subprocess descriptions
# (313-429 chars across a representative sample), same margin used for
# process_steps[].description in process_json.py.
MIN_SUBSTEP_DESCRIPTION_CHARS = 150


def validate_subprocess_flow(flow: Dict[str, Any]) -> Dict[str, Any]:
    """Checked before every save -- a sub-step missing these fields doesn't
    fail loudly anywhere else: the document renderer silently falls back to
    a generic "Sub-step N" heading (missing substep_name) or simply omits a
    section (any other missing field), instead of raising, so a generation
    that drops them (observed from the model despite the generator agent's
    own instructions listing them all as required) would otherwise only
    surface as a suspiciously thin document, long after this tool call
    succeeded. purpose/scope have no length minimum -- the reference
    document's own values for these are sometimes a single short clause
    (e.g. scope: "Program level") -- only description needs real prose."""
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
        description = sub.get("description")
        if not description:
            issues.append({"location": f"{loc}.description", "issue": "description is required"})
        elif len(description) < MIN_SUBSTEP_DESCRIPTION_CHARS:
            issues.append({
                "location": f"{loc}.description",
                "issue": (
                    f"description is too thin ({len(description)} chars, need "
                    f"{MIN_SUBSTEP_DESCRIPTION_CHARS}+) -- explain what happens in this sub-step, how, "
                    "and what it produces, not just a one-clause summary."
                ),
            })
        for field in ("purpose", "scope", "process_owner", "responsible_party"):
            if not sub.get(field):
                issues.append({"location": f"{loc}.{field}", "issue": f"{field} is required"})

    return {"valid": not issues, "issues": issues}


def save_subprocess_flow(step_name: str, flow: Dict[str, Any]) -> Dict[str, Any]:
    validation = validate_subprocess_flow(flow)
    if not validation["valid"]:
        # WARNING, not DEBUG: same reasoning as persist_final_json -- this
        # is the diagnostic for "why is this step's subprocess missing or
        # generic-looking in the document," visible without raising LOGLEVEL.
        logger.warning(
            "Subprocess_Generator_Agent's flow for step %r failed validation, nothing persisted: %s",
            step_name, validation["issues"],
        )
        return {"status": "ERROR", "error": "Invalid subprocess_flow.", "issues": validation["issues"]}

    subprocess_dir = paths.output_dir("subprocesses")

    safe_name = safe_filename_component(step_name)
    file_path = os.path.join(subprocess_dir, f"{safe_name}.json")

    resolved_dir = os.path.realpath(subprocess_dir)
    resolved_path = os.path.realpath(file_path)
    if os.path.commonpath([resolved_dir, resolved_path]) != resolved_dir:
        logger.error(
            "Refused to write subprocess flow outside %s: step_name=%r resolved to %r -- "
            "likely an LLM-generated step_name containing path-traversal characters.",
            subprocess_dir, step_name, resolved_path,
        )
        return {
            "status": "ERROR",
            "error": f"Refusing to write outside {subprocess_dir}: step_name={step_name!r} resolved to {resolved_path!r}",
        }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(flow, f, indent=2)
        logger.info(
            "Persisted subprocess flow for step %r to %s (%d sub-step(s)).",
            step_name, file_path, len(flow.get("subprocess_flow") or []),
        )
        return {"status": "OK", "path": file_path}
    except Exception as e:
        logger.exception("Failed to write subprocess flow for step %r to %s.", step_name, file_path)
        return {"status": "ERROR", "error": str(e)}
