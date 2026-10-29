"""Requirements-summary lightweight structural validation + old-format
detection.

requirements_summary.py's own save_requirements_summary stays untouched
(zero validation -- any dict passes, by design, documented there) -- this
module exists only for process_toolkit.docgen.requirements_sections.py's
own rendering branches (picking the current vs. old-format renderer) and
for test coverage, not as a new persistence gate.
"""

import json
from typing import Any, Dict, List

from process_toolkit.requirements_summary.requirements_summary import (  # noqa: F401
    REQUIREMENTS_SUMMARY_FILENAME,
)

_VALID_REQUIREMENT_TYPES = {"functional", "non_functional", "goal", "constraint"}

# Legacy flat-string-array shape some older summaries used, predating the
# requirements_register -- the "OLD-FORMAT FALLBACK" every existing
# consumer (Requirements_Summary_Agent, Requirements_Consultant_Agent)
# already documents in its own instruction prose.
_OLD_FORMAT_KEYS = (
    "functional_requirements",
    "non_functional_requirements",
    "goals_or_objectives",
    "constraints",
)

# One-item example shapes, matching design_json.py's/process_json.py's own
# template convention -- for test fixtures and documentation only, never
# consumed by the save path.
REQUIREMENTS_SUMMARY_TEMPLATE: Dict[str, Any] = {
    "source_directory": "",
    "source_files": [],
    "summary": "",
    "industry_sector": "",
    "stakeholders": [],
    "assumptions": [],
    "risks": [],
    "open_questions": [],
    "requirements_register": [
        {
            "id": "FR-001",
            "type": "functional",
            "description": "",
            "source": "",
            "acceptance_criteria": [],
            "status": "proposed",
        }
    ],
    "requirement_priorities": [
        {"requirement_id": "", "requirement_text": "", "priority": "medium", "rationale": ""}
    ],
    "conflicting_requirements": [
        {"requirement_ids": [], "requirements_text": [], "description": "", "recommendation": ""}
    ],
    "requirements_needing_clarification": [
        {"requirement_id": "", "requirement_text": "", "question": ""}
    ],
    "inferred_requirements": [
        {
            "id": "INF-001",
            "requirement": "",
            "rationale": "",
            "category": "functional",
            "derived_from": [],
            "acceptance_criteria": [],
        }
    ],
    "coverage_gaps": [{"category": "", "description": ""}],
}


def load_requirements_summary_template() -> Dict[str, Any]:
    return json.loads(json.dumps(REQUIREMENTS_SUMMARY_TEMPLATE))


def is_old_format_requirements_summary(data: Any) -> bool:
    """True when `data` has one of the legacy flat string-array fields and
    no (non-empty) requirements_register -- the shape every existing
    consumer's own "OLD-FORMAT FALLBACK" instructions already handle
    narratively."""
    if not isinstance(data, dict):
        return False
    if isinstance(data.get("requirements_register"), list) and data["requirements_register"]:
        return False
    return any(isinstance(data.get(key), list) for key in _OLD_FORMAT_KEYS)


def validate_requirements_summary(json_content: Any) -> Dict[str, Any]:
    """Soft structural check -- NOT wired into save_requirements_summary's
    own save path (that stays zero-validation, by design). Used by the
    docgen renderer to decide which rendering branch to use, and by tests.
    Mirrors validate_design_json's own shape/severity convention (a flat
    issues list, "valid" is just "no issues found")."""
    issues: List[Dict[str, str]] = []

    if not isinstance(json_content, dict):
        return {"valid": False, "issues": [{"location": "$", "issue": "Input is not a JSON object"}]}

    if is_old_format_requirements_summary(json_content):
        # The legacy flat-array shape has no ids/types/sources to check --
        # the renderer's own old-format branch handles it as plain bullets.
        return {"valid": True, "issues": []}

    register = json_content.get("requirements_register")
    if not isinstance(register, list):
        return {
            "valid": False,
            "issues": [{"location": "requirements_register", "issue": "requirements_register must be a list"}],
        }

    seen_ids = set()
    for index, item in enumerate(register):
        if not isinstance(item, dict):
            issues.append({"location": f"requirements_register[{index}]", "issue": "Each entry must be an object"})
            continue

        req_id = str(item.get("id") or "").strip()
        if not req_id:
            issues.append({
                "location": f"requirements_register[{index}].id",
                "issue": "A stable identifier is required, e.g. 'FR-001'",
            })
        elif req_id in seen_ids:
            issues.append({"location": f"requirements_register[{index}].id", "issue": f"Duplicate id '{req_id}'"})
        else:
            seen_ids.add(req_id)

        req_type = item.get("type")
        if req_type not in _VALID_REQUIREMENT_TYPES:
            issues.append({
                "location": f"requirements_register[{index}].type",
                "issue": f"type must be one of {sorted(_VALID_REQUIREMENT_TYPES)}, got '{req_type}'",
            })

        if not str(item.get("description") or "").strip():
            issues.append({
                "location": f"requirements_register[{index}].description",
                "issue": "A description is required",
            })

    # Soft cross-reference checks -- these lists SHOULD name a real
    # register id; a dangling reference is a quality issue worth
    # surfacing, same as the structural checks above.
    for list_key, id_field in (
        ("requirement_priorities", "requirement_id"),
        ("requirements_needing_clarification", "requirement_id"),
    ):
        for index, item in enumerate(json_content.get(list_key) or []):
            if not isinstance(item, dict):
                continue
            ref_id = item.get(id_field)
            if ref_id and ref_id not in seen_ids:
                issues.append({
                    "location": f"{list_key}[{index}].{id_field}",
                    "issue": f"References unknown requirement id '{ref_id}'",
                })

    for index, item in enumerate(json_content.get("conflicting_requirements") or []):
        if not isinstance(item, dict):
            continue
        for ref_id in item.get("requirement_ids") or []:
            if ref_id not in seen_ids:
                issues.append({
                    "location": f"conflicting_requirements[{index}].requirement_ids",
                    "issue": f"References unknown requirement id '{ref_id}'",
                })

    return {"valid": len(issues) == 0, "issues": issues}
