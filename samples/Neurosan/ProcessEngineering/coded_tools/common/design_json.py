"""Design-document JSON persistence + lightweight structural validation.
Design-schema counterpart to process_json.py -- same save/load/template-
fallback shape, validating against design_document_schema.json's structural
essentials (document_metadata's required fields, document_type enum, the
conditional high_level_design/low_level_design requirement) rather than the
full JSON-Schema document, the same simplification process_json.py already
makes for the process schema.
"""

import json
import os
from typing import Any, Dict, List, Optional

from coded_tools.common.paths import output_path
from coded_tools.common.process_json import DESIGN_JSON_FILENAME

DESIGN_TEMPLATE: Dict[str, Any] = {
    "document_metadata": {
        "document_id": "",
        "document_type": "",
        "system_name": "",
        "title": "",
        "version": "1.0",
        "status": "draft",
    },
    "business_context": {},
    "architecture_description": {},
    "requirements": {},
    "system_context": {},
    "high_level_design": {},
    "low_level_design": {},
    "quality_attributes": [],
    "compliance_and_standards": {},
    "risk_register": [],
    "governance_requirements": [],
    "continuous_improvement": [],
    "glossary_and_references": {},
    "appendix": {},
}

_VALID_DOCUMENT_TYPES = {"HLD", "LLD", "Combined"}


def load_design_template() -> Dict[str, Any]:
    return json.loads(json.dumps(DESIGN_TEMPLATE))


def load_master_design_json() -> Dict[str, Any]:
    """Returns the existing baseline if present, else the empty template --
    ALWAYS returns a valid JSON object, the generator never needs to
    construct one from scratch."""
    path = output_path(DESIGN_JSON_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return load_design_template()


def load_full_design_context() -> Dict[str, Any]:
    """Same content as load_master_design_json -- kept as a separate name
    for the consultant/scenario-tester/simulation-query agents, matching
    the ADK original's distinct tool name for the same underlying data."""
    return load_master_design_json()


def validate_design_json(json_content: Any) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []

    if not isinstance(json_content, dict):
        return {"valid": False, "issues": [{"location": "$", "issue": "Input is not a JSON object"}]}

    metadata = json_content.get("document_metadata")
    if not isinstance(metadata, dict):
        issues.append({
            "location": "document_metadata",
            "issue": (
                "document_metadata is required and must be an object. If this document has very "
                "few top-level keys, you may have submitted only a delta instead of the full "
                "merged document -- always load the baseline and persist the whole thing."
            ),
        })
        return {"valid": False, "issues": issues}

    for field in ("document_id", "document_type", "system_name", "title", "version", "status"):
        if not metadata.get(field):
            issues.append({"location": f"document_metadata.{field}", "issue": f"'{field}' is required"})

    document_type = metadata.get("document_type")
    if document_type and document_type not in _VALID_DOCUMENT_TYPES:
        issues.append({
            "location": "document_metadata.document_type",
            "issue": f"document_type must be one of {sorted(_VALID_DOCUMENT_TYPES)}, got '{document_type}'",
        })

    if document_type in ("HLD", "Combined") and not isinstance(json_content.get("high_level_design"), dict):
        issues.append({
            "location": "high_level_design",
            "issue": f"high_level_design is required when document_type is '{document_type}'",
        })
    if document_type in ("LLD", "Combined") and not isinstance(json_content.get("low_level_design"), dict):
        issues.append({
            "location": "low_level_design",
            "issue": f"low_level_design is required when document_type is '{document_type}'",
        })

    return {"valid": len(issues) == 0, "issues": issues}


def persist_final_design_json(json_content: Any) -> str:
    if not json_content or (isinstance(json_content, dict) and len(json_content) == 0):
        return "INFO: No JSON content provided, so nothing has been done."

    if isinstance(json_content, str):
        try:
            json_content = json.loads(json_content)
        except Exception as e:
            return f"ERROR: Could not parse JSON content: {e}"

    validation = validate_design_json(json_content)
    if not validation["valid"]:
        return f"ERROR: JSON failed validation: {validation['issues']}"

    path = output_path(DESIGN_JSON_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(json_content, f, indent=2, ensure_ascii=False)
        return f"SUCCESS: The file {path} was saved successfully."
    except Exception as e:
        return f"ERROR: Could not save design JSON: {e}"


def extract_valid_json(raw: str) -> Optional[Dict[str, Any]]:
    """Brace-balanced JSON object extractor for a possibly-noisy LLM string
    -- identical algorithm to process_json.py's extract_valid_json, kept as
    its own copy here so design_json.py has no import dependency on the
    process-schema module for something this small."""
    import re
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
