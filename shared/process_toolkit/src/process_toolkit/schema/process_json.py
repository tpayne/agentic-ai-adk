"""Process JSON persistence + lightweight structural validation.

Checks a minimal, functionally-essential set of structural rules (required
top-level fields exist; every process_step has a step_name and a
responsible_party; dependencies reference real step names) rather than a
full JSON-Schema document. The save/load/template-fallback *behavior* --
not an exhaustive schema -- is what's preserved.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from process_toolkit import paths

PROCESS_JSON_FILENAME = "process_data.json"
# Written by the design pipeline (design_json.py) -- kept here, not there,
# so detect_schema_type_from_disk below (needed regardless of which schema
# is active) has no import-cycle back into design_json.py.
DESIGN_JSON_FILENAME = "design_data.json"


def detect_schema_type_from_disk() -> str:
    """"design" only when design_data.json exists AND process_data.json
    does NOT -- i.e. an unambiguous design-only workspace. Every other
    case (only process exists, both exist, or neither exists) resolves to
    "process"."""
    design_path = paths.output_path(DESIGN_JSON_FILENAME)
    process_path = paths.output_path(PROCESS_JSON_FILENAME)
    if os.path.exists(design_path) and not os.path.exists(process_path):
        return "design"
    return "process"


# One-item example lists give the generating agent a concrete structural
# hint for every list/object field (rather than a bare `[]`/`""`), so it
# naturally lands on the keys the docgen renderers actually expect instead
# of improvising an internally-consistent but mismatched shape.
PROCESS_TEMPLATE: Dict[str, Any] = {
    "process_name": "",
    "version": "1.0",
    "introduction": "",
    "purpose": "",
    "scope": "",
    "process_owner": "",
    "industry_sector": "",
    "stakeholders": [{"stakeholder_name": "", "role": "", "responsibilities": []}],
    "process_steps": [],
    "process_goals": [],
    "system_requirements": [{"name": "", "details": ""}],
    "tools_summary": [{"category": "", "tools": []}],
    "metrics": [{"name": "", "description": "", "measurement_frequency": "", "target": ""}],
    "critical_success_factors": [{"name": "", "description": ""}],
    "critical_failure_factors": [{"name": "", "description": ""}],
    "constraints": [],
    "assumptions": [],
    "process_triggers": [],
    "process_end_conditions": [],
    "risks_and_controls": [{"risk": "", "control": ""}],
    "governance_requirements": [],
    "change_management": [{"change_request_process": "", "versioning_rules": ""}],
    "continuous_improvement": [{"review_frequency": "", "improvement_inputs": []}],
    "reporting_and_analytics": [{"metric": "", "description": ""}],
    "requirements_register": [],
    "appendix": {},
}


def load_process_template() -> Dict[str, Any]:
    return json.loads(json.dumps(PROCESS_TEMPLATE))


def load_master_process_json() -> Dict[str, Any]:
    """Returns the existing baseline if present, else the empty template --
    load_master_process_json ALWAYS returns a valid JSON object, the
    generator never needs to construct one from scratch."""
    path = paths.output_path(PROCESS_JSON_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return load_process_template()


def load_full_process_context() -> Dict[str, Any]:
    """Same content as load_master_process_json -- kept as a separate name
    for the consultant/scenario agents."""
    return load_master_process_json()


def validate_process_json(json_content: Any) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []

    if not isinstance(json_content, dict):
        return {"valid": False, "issues": [{"location": "$", "issue": "Input is not a JSON object"}]}

    for field in ("process_name", "process_steps"):
        if field not in json_content:
            issues.append({"location": field, "issue": f"Missing required field '{field}'"})

    steps = json_content.get("process_steps")
    step_names = set()
    if isinstance(steps, list):
        for i, step in enumerate(steps):
            loc = f"process_steps[{i}]"
            if not isinstance(step, dict):
                issues.append({"location": loc, "issue": "Each process step must be an object"})
                continue
            if not step.get("step_name"):
                issues.append({"location": f"{loc}.step_name", "issue": "step_name is required"})
            else:
                step_names.add(step["step_name"])
            if not step.get("responsible_party"):
                issues.append({"location": f"{loc}.responsible_party", "issue": "responsible_party is required"})
    elif "process_steps" in json_content:
        issues.append({"location": "process_steps", "issue": "process_steps must be a list"})

    if isinstance(steps, list):
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            deps = step.get("dependencies") or []
            if isinstance(deps, str):
                deps = [deps]
            for dep in deps:
                if dep not in step_names:
                    issues.append({
                        "location": f"process_steps[{i}].dependencies",
                        "issue": f"Dependency '{dep}' does not match any step_name in this document",
                    })

    # A hard validation gate (like step_name/responsible_party above), not
    # just a prose request in the generating agent's instructions -- a
    # prose-only ask was not enough to stop a live model from emitting bare
    # {"id", "<name>"} objects with no description, leaving the rendered
    # Metrics/CSF/CFF/Reporting tables with a blank Description column.
    for field, name_key in (
        ("metrics", "metric"),
        ("critical_success_factors", "factor"),
        ("critical_failure_factors", "factor"),
        ("reporting_and_analytics", "report"),
    ):
        items = json_content.get(field)
        if not isinstance(items, list):
            continue
        for i, item in enumerate(items):
            loc = f"{field}[{i}]"
            if not isinstance(item, dict):
                continue
            if not item.get(name_key) and not item.get("name"):
                issues.append({"location": loc, "issue": f"'{name_key}' (or 'name') is required"})
            if not item.get("description"):
                issues.append({"location": f"{loc}.description", "issue": "description is required"})

    return {"valid": len(issues) == 0, "issues": issues}


def persist_final_json(json_content: Any) -> str:
    if not json_content or (isinstance(json_content, dict) and len(json_content) == 0):
        return "INFO: No JSON content provided, so nothing has been done."

    if isinstance(json_content, str):
        try:
            json_content = json.loads(json_content)
        except Exception as e:
            return f"ERROR: Could not parse JSON content: {e}"

    validation = validate_process_json(json_content)
    if not validation["valid"]:
        return f"ERROR: JSON failed validation: {validation['issues']}"

    path = paths.output_path(PROCESS_JSON_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(json_content, f, indent=2, ensure_ascii=False)
        return f"SUCCESS: The file {path} was saved successfully."
    except Exception as e:
        return f"ERROR: Could not save process JSON: {e}"


def extract_valid_json(raw: str) -> Optional[Dict[str, Any]]:
    """Brace-balanced JSON object extractor for a possibly-noisy LLM string
    (leading/trailing commentary, markdown fences, trailing commas)."""
    raw = raw.strip()
    stack = []
    start_idx = None
    candidates = []
    for i, ch in enumerate(raw):
        if ch == "{":
            if not stack:
                start_idx = i
            stack.append("{")
        elif ch == "}":
            if stack:
                stack.pop()
                if not stack and start_idx is not None:
                    candidates.append(raw[start_idx:i + 1])
                    start_idx = None

    for block in sorted(candidates, key=len, reverse=True):
        try:
            return json.loads(block)
        except Exception:
            repaired = re.sub(r",\s*([\]}])", r"\1", block).replace("﻿", "")
            try:
                return json.loads(repaired)
            except Exception:
                continue
    return None
