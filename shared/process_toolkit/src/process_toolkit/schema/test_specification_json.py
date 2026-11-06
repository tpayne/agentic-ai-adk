"""Test-specification lightweight structural validation.

Mirrors requirements_json.py's own convention exactly: a one-item
TEMPLATE for documentation/test-fixture parity, and a soft validator
used by the docgen renderer (never wired into the save path itself,
which stays zero-validation by design, same as every other artifact
type in this toolkit).
"""

import json
from typing import Any, Dict, List

TEST_SPECIFICATION_FILENAME = "test_specification.json"

_VALID_TEST_TYPES = {
    "functional", "non_functional", "security", "performance",
    "integration", "usability", "compliance", "infrastructure",
}
_VALID_SOURCE_ARTIFACTS = {"requirements", "design", "cloudarch", "multiple"}

# One-item example shape, matching requirements_json.py's own template
# convention -- for test fixtures and documentation only, never
# consumed by the save path.
TEST_SPECIFICATION_TEMPLATE: Dict[str, Any] = {
    "name": "",
    "source_requirements_used": False,
    "source_design_used": False,
    "source_cloudarch_used": False,
    "summary": "",
    "test_approach": "",
    "test_environment": "",
    "test_cases": [
        {
            "id": "TC-001",
            "title": "",
            "type": "functional",
            "description": "",
            "preconditions": [],
            "steps": [],
            "test_data": "",
            "expected_result": "",
            "acceptance_criteria": [],
            "priority": "medium",
            "status": "proposed",
            "traces_to": [],
            "source_artifact": "requirements",
            "verification_method": "",
            "owner": "",
        }
    ],
    "coverage_summary": {
        "requirements_covered": [],
        "requirements_not_covered": [],
        "design_components_covered": [],
        "design_components_not_covered": [],
        "cloudarch_components_covered": [],
        "cloudarch_components_not_covered": [],
    },
    "risks": [],
    "open_questions": [],
    "dependencies": [{"dependency": "", "description": "", "status": ""}],
    "glossary": [{"term": "", "definition": ""}],
}


def load_test_specification_template() -> Dict[str, Any]:
    return json.loads(json.dumps(TEST_SPECIFICATION_TEMPLATE))


def validate_test_specification(json_content: Any) -> Dict[str, Any]:
    """Soft structural check -- NOT wired into save_test_specification's
    own save path (that stays zero-validation, by design). Used by the
    docgen renderer to decide rendering details and by tests. Mirrors
    validate_requirements_summary's own shape/severity convention (a
    flat issues list, "valid" is just "no issues found")."""
    issues: List[Dict[str, str]] = []

    if not isinstance(json_content, dict):
        return {"valid": False, "issues": [{"location": "$", "issue": "Input is not a JSON object"}]}

    test_cases = json_content.get("test_cases")
    if not isinstance(test_cases, list):
        return {
            "valid": False,
            "issues": [{"location": "test_cases", "issue": "test_cases must be a list"}],
        }

    seen_ids = set()
    for index, item in enumerate(test_cases):
        if not isinstance(item, dict):
            issues.append({"location": f"test_cases[{index}]", "issue": "Each entry must be an object"})
            continue

        tc_id = str(item.get("id") or "").strip()
        if not tc_id:
            issues.append({
                "location": f"test_cases[{index}].id",
                "issue": "A stable identifier is required, e.g. 'TC-001'",
            })
        elif tc_id in seen_ids:
            issues.append({"location": f"test_cases[{index}].id", "issue": f"Duplicate id '{tc_id}'"})
        else:
            seen_ids.add(tc_id)

        tc_type = item.get("type")
        if tc_type not in _VALID_TEST_TYPES:
            issues.append({
                "location": f"test_cases[{index}].type",
                "issue": f"type must be one of {sorted(_VALID_TEST_TYPES)}, got '{tc_type}'",
            })

        if not str(item.get("description") or "").strip():
            issues.append({
                "location": f"test_cases[{index}].description",
                "issue": "A description is required",
            })

        if not str(item.get("expected_result") or "").strip():
            issues.append({
                "location": f"test_cases[{index}].expected_result",
                "issue": "An expected_result is required -- a test case with no defined pass/fail "
                         "criterion cannot actually be executed",
            })

        source_artifact = item.get("source_artifact")
        if source_artifact is not None and source_artifact not in _VALID_SOURCE_ARTIFACTS:
            issues.append({
                "location": f"test_cases[{index}].source_artifact",
                "issue": f"source_artifact must be one of {sorted(_VALID_SOURCE_ARTIFACTS)}, got '{source_artifact}'",
            })

    return {"valid": len(issues) == 0, "issues": issues}
