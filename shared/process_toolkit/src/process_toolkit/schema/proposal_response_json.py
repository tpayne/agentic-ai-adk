"""Proposal-response lightweight structural validation.

proposal_response.py's own save_proposal_response stays untouched (zero
validation -- any dict passes, by design, documented there) -- this
module exists only for process_toolkit.docgen.proposal_response_sections.py's
own rendering, and for test coverage, not as a new persistence gate.
Unlike requirements_json.py, there is no legacy/old-format shape to
detect here -- proposal_response.json is a brand-new artifact.
"""

import json
from typing import Any, Dict, List

from process_toolkit.proposal_response.proposal_response import (  # noqa: F401
    PROPOSAL_RESPONSE_FILENAME,
)

_VALID_RESPONSE_STATUSES = {
    "Fully Compliant",
    "Partially Compliant",
    "Not Compliant",
    "Exception",
}

# One-item example shape, matching requirements_json.py's own template
# convention -- for test fixtures and documentation only, never consumed
# by the save path.
PROPOSAL_RESPONSE_TEMPLATE: Dict[str, Any] = {
    "summary": "",
    "our_understanding": "",
    "proposed_solution": "",
    "architecture_components": [
        {"name": "", "description": "", "connects_to": []}
    ],
    "differentiators": [],
    "compliance_matrix": [
        {
            "requirement_id": "FR-001",
            "requirement_text": "",
            "requirement_type": "functional",
            "response_status": "Fully Compliant",
            "response": "",
        }
    ],
    "assumptions": [],
    "risks_and_mitigations": [{"risk": "", "mitigation": ""}],
    "qualifications": "",
    "pricing_approach": "",
    "open_questions_for_client": [],
    "unaddressed_items": [],
}


def load_proposal_response_template() -> Dict[str, Any]:
    return json.loads(json.dumps(PROPOSAL_RESPONSE_TEMPLATE))


def validate_proposal_response(json_content: Any) -> Dict[str, Any]:
    """Soft structural check -- NOT wired into save_proposal_response's own
    save path (that stays zero-validation, by design). Used by the docgen
    renderer to decide whether compliance_matrix entries are well-formed,
    and by tests. Mirrors validate_requirements_summary's own shape/
    severity convention (a flat issues list, "valid" is just "no issues
    found")."""
    issues: List[Dict[str, str]] = []

    if not isinstance(json_content, dict):
        return {"valid": False, "issues": [{"location": "$", "issue": "Input is not a JSON object"}]}

    matrix = json_content.get("compliance_matrix")
    if matrix is not None:
        if not isinstance(matrix, list):
            issues.append({"location": "$.compliance_matrix", "issue": "compliance_matrix must be a list"})
        else:
            for i, entry in enumerate(matrix):
                location = f"$.compliance_matrix[{i}]"
                if not isinstance(entry, dict):
                    issues.append({"location": location, "issue": "entry must be an object"})
                    continue
                if not entry.get("requirement_id"):
                    issues.append({"location": location, "issue": "missing requirement_id"})
                status = entry.get("response_status")
                if status not in _VALID_RESPONSE_STATUSES:
                    issues.append({
                        "location": f"{location}.response_status",
                        "issue": f"must be one of {sorted(_VALID_RESPONSE_STATUSES)}, got {status!r}",
                    })

    return {"valid": len(issues) == 0, "issues": issues}
