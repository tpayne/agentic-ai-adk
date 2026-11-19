"""ITSM (IT Service Management) process document JSON persistence +
lightweight structural validation. Same save/load/template-fallback shape
as togaf_json.py/design_json.py -- validating against the structural
essentials (document_metadata's required fields, per-list required-field
checks) rather than a full JSON-Schema document.

Scope (deliberate, not exhaustive ITIL coverage): Incident Management,
Problem Management, Change Management (CAB/RFC/risk), Request Fulfillment,
Service Level Management (SLA/OLA/underpinning contracts), a Service
Catalog, a light Configuration Management database (CIs + relationships
only -- no discovery/reconciliation modeling), roles/RACI, and a tooling
inventory. Deliberately NO cost/date/staffing-count field anywhere in this
schema (enforced by absence, the same anti-fabrication discipline
togaf_json.py's own migration_planning and design_json.py's own
architecture_decisions already use) -- Capacity/Availability Management,
Continual Service Improvement metrics, Financial Management for IT
Services, Release/Deployment detail, and Knowledge Management are all OUT
OF SCOPE: each is an ongoing measurement/governance practice, not a
point-in-time document artifact a generator can produce.

Single rendered document (no Vision/Definition-style variant split the
way togaf_json.py has) -- docgen/generation.py renders schema_type="itsm"
as one file, the same as requirements_json.py/proposal_response_json.py/
test_specification_json.py.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.ItsmJson")

ITSM_JSON_FILENAME = "itsm_data.json"

# One-item example shapes (not bare `{}`/`[]`) so the generating agent
# lands on real key names -- same reasoning as TOGAF_TEMPLATE's own header
# comment.
ITSM_TEMPLATE: Dict[str, Any] = {
    "document_metadata": {
        "document_id": "",
        "system_name": "",
        "title": "",
        "version": "1.0",
        "status": "draft",
    },

    "service_catalog": {
        "services": [
            {
                "id": "SVC-001", "name": "", "description": "", "category": "",
                "business_criticality": "", "owner": "",
            }
        ],
    },

    "stakeholders_and_roles": [
        {"role": "", "responsibilities": [], "escalation_tier": ""}
    ],

    "incident_management": {
        "priority_matrix": [
            {
                "priority": "P1", "impact": "", "urgency": "",
                "target_response_time": "", "target_resolution_time": "",
            }
        ],
        "process_steps": [
            {
                "step_id": "", "step_name": "", "description": "",
                "responsible_role": "", "inputs": [], "outputs": [],
            }
        ],
        "process_flow_diagram": {
            "diagram_id": "", "diagram_type": "edge_graph", "title": "", "description": "",
        },
        "escalation_paths": [
            {"from_tier": "", "to_tier": "", "trigger_condition": ""}
        ],
    },

    "problem_management": {
        "process_steps": [
            {
                "step_id": "", "step_name": "", "description": "",
                "responsible_role": "", "inputs": [], "outputs": [],
            }
        ],
        "process_flow_diagram": {
            "diagram_id": "", "diagram_type": "edge_graph", "title": "", "description": "",
        },
        # linked_incidents cross-refs incident_management -- never a fresh
        # incident id invented here.
        "known_errors": [
            {"id": "KE-001", "description": "", "workaround": "", "linked_incidents": []}
        ],
    },

    "change_management": {
        "change_types": [
            {"type": "standard", "description": "", "approval_path": ""}
        ],
        "process_steps": [
            {
                "step_id": "", "step_name": "", "description": "",
                "responsible_role": "", "inputs": [], "outputs": [],
            }
        ],
        "process_flow_diagram": {
            "diagram_id": "", "diagram_type": "edge_graph", "title": "", "description": "",
        },
        "cab_members": [{"role": "", "name_or_title": ""}],
        "risk_assessment_criteria": [
            {"risk_level": "", "criteria": "", "required_approvals": []}
        ],
    },

    "request_fulfillment": {
        "request_types": [
            {"type": "", "description": "", "target_fulfillment_time": ""}
        ],
        "process_steps": [
            {
                "step_id": "", "step_name": "", "description": "",
                "responsible_role": "", "inputs": [], "outputs": [],
            }
        ],
        "process_flow_diagram": {
            "diagram_id": "", "diagram_type": "edge_graph", "title": "", "description": "",
        },
    },

    "service_level_management": {
        "slas": [
            {"id": "SLA-001", "service_id": "", "metric": "", "target": "", "measurement_window": ""}
        ],
        "olas": [{"id": "OLA-001", "internal_team": "", "metric": "", "target": ""}],
        "underpinning_contracts": [
            {"id": "UC-001", "vendor": "", "scope": "", "linked_sla": ""}
        ],
    },

    # Light CMDB -- CIs + relationships only, no discovery/reconciliation
    # modeling, no lifecycle-state tracking.
    "configuration_management": {
        "configuration_items": [{"id": "CI-001", "name": "", "type": "", "owner": ""}],
        "relationships": [
            {"source_ci": "", "target_ci": "", "relationship_type": ""}
        ],
        "relationship_diagram": {
            "diagram_id": "", "diagram_type": "edge_graph", "title": "", "description": "",
        },
    },

    # Cross-process RACI -- every row names which process area it belongs
    # to, so one table can cover incident/problem/change/request/SLM
    # governance without needing a separate RACI per process.
    "raci_matrix": [
        {
            "process_area": "", "activity": "", "responsible": "",
            "accountable": "", "consulted": "", "informed": "",
        }
    ],

    "tooling_and_platform": [{"category": "", "tool_name": "", "purpose": ""}],

    "risks_and_controls": [{"risk": "", "control": ""}],

    "glossary_and_references": {
        "glossary": [{"term": "", "definition": ""}],
        "references": [{"title": "", "source": "", "url": ""}],
    },
    "appendix": {},
}


def load_itsm_template() -> Dict[str, Any]:
    return json.loads(json.dumps(ITSM_TEMPLATE))


def load_master_itsm_json() -> Dict[str, Any]:
    """Returns the existing baseline if present, else the empty template --
    ALWAYS returns a valid JSON object, the generator never needs to
    construct one from scratch."""
    path = paths.output_path(ITSM_JSON_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.debug("Loaded existing ITSM baseline from %s.", path)
            return data
        except Exception:
            logger.exception(
                "Existing ITSM baseline at %s exists but could not be read -- falling back to the "
                "empty template. Any un-persisted work in that file is NOT reflected in what gets returned.",
                path,
            )
    else:
        logger.debug("No ITSM baseline at %s -- falling back to the empty template.", path)
    return load_itsm_template()


def load_full_itsm_context() -> Dict[str, Any]:
    """Same content as load_master_itsm_json -- kept as a separate name
    for the scenario-tester/reviewer/consultant agents."""
    return load_master_itsm_json()


def _validate_list_items(
    items: Any, location_prefix: str, required_fields: tuple, issues: List[Dict[str, str]]
) -> None:
    """Shared list-of-objects check, identical shape to togaf_json.py's own
    helper of this name. A missing/not-yet-a-list field is not itself an
    issue -- mid-generation documents legitimately have unfilled sections --
    but a non-dict item inside a present list is flagged rather than
    silently skipped."""
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append({
                "location": f"{location_prefix}[{index}]",
                "issue": f"Expected an object with field(s) {list(required_fields)}, got {type(item).__name__}",
            })
            continue
        for field in required_fields:
            if not str(item.get(field) or "").strip():
                issues.append({
                    "location": f"{location_prefix}[{index}].{field}",
                    "issue": f"'{field}' is required",
                })


def _validate_process_steps(container: Any, location_prefix: str, issues: List[Dict[str, str]]) -> None:
    """Shared check for the four process_steps lists (incident/problem/
    change/request_fulfillment all have the same shape) -- avoids
    duplicating the same four _validate_list_items calls."""
    if not isinstance(container, dict):
        return
    _validate_list_items(container.get("process_steps"), f"{location_prefix}.process_steps", ("step_id", "step_name"), issues)


def validate_itsm_json(json_content: Any) -> Dict[str, Any]:
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

    for field in ("document_id", "system_name", "title", "version", "status"):
        if not metadata.get(field):
            issues.append({"location": f"document_metadata.{field}", "issue": f"'{field}' is required"})

    service_catalog = json_content.get("service_catalog")
    if isinstance(service_catalog, dict):
        _validate_list_items(service_catalog.get("services"), "service_catalog.services", ("id", "name"), issues)

    incident_management = json_content.get("incident_management")
    if isinstance(incident_management, dict):
        _validate_list_items(
            incident_management.get("priority_matrix"),
            "incident_management.priority_matrix",
            ("priority", "impact", "urgency"),
            issues,
        )
        _validate_process_steps(incident_management, "incident_management", issues)

    problem_management = json_content.get("problem_management")
    if isinstance(problem_management, dict):
        _validate_process_steps(problem_management, "problem_management", issues)

    change_management = json_content.get("change_management")
    if isinstance(change_management, dict):
        _validate_list_items(
            change_management.get("change_types"),
            "change_management.change_types",
            ("type", "approval_path"),
            issues,
        )
        _validate_process_steps(change_management, "change_management", issues)

    request_fulfillment = json_content.get("request_fulfillment")
    if isinstance(request_fulfillment, dict):
        _validate_process_steps(request_fulfillment, "request_fulfillment", issues)

    service_level_management = json_content.get("service_level_management")
    if isinstance(service_level_management, dict):
        _validate_list_items(
            service_level_management.get("slas"),
            "service_level_management.slas",
            ("id", "metric", "target"),
            issues,
        )

    configuration_management = json_content.get("configuration_management")
    if isinstance(configuration_management, dict):
        _validate_list_items(
            configuration_management.get("configuration_items"),
            "configuration_management.configuration_items",
            ("id", "name"),
            issues,
        )
        _validate_list_items(
            configuration_management.get("relationships"),
            "configuration_management.relationships",
            ("source_ci", "target_ci"),
            issues,
        )

    _validate_list_items(
        json_content.get("raci_matrix"), "raci_matrix", ("process_area", "activity"), issues
    )

    return {"valid": len(issues) == 0, "issues": issues}


def persist_final_itsm_json(json_content: Any) -> str:
    if not json_content or (isinstance(json_content, dict) and len(json_content) == 0):
        logger.debug("persist_final_itsm_json called with no content -- nothing to do.")
        return "INFO: No JSON content provided, so nothing has been done."

    if isinstance(json_content, str):
        try:
            json_content = json.loads(json_content)
        except Exception as e:
            logger.warning("persist_final_itsm_json received a string that is not valid JSON: %s", e)
            return f"ERROR: Could not parse JSON content: {e}"

    validation = validate_itsm_json(json_content)
    if not validation["valid"]:
        # INFO, not WARNING -- same reasoning as togaf_json.py's own
        # persist_final_togaf_json: this fires on routine mid-process
        # validate-and-retry attempts, not just a final failure.
        logger.info("ITSM_Agent's ITSM JSON failed validation, nothing persisted: %s", validation["issues"])
        return f"ERROR: JSON failed validation: {validation['issues']}"

    path = paths.output_path(ITSM_JSON_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(json_content, f, indent=2, ensure_ascii=False)
        logger.info("Persisted ITSM JSON to %s.", path)
        return f"SUCCESS: The file {path} was saved successfully."
    except Exception as e:
        logger.exception("Failed to write ITSM JSON to %s.", path)
        return f"ERROR: Could not save ITSM JSON: {e}"


def extract_valid_json(raw: str) -> Optional[Dict[str, Any]]:
    """Brace-balanced JSON object extractor for a possibly-noisy LLM
    string -- identical algorithm to togaf_json.py's/design_json.py's own
    extract_valid_json."""
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
