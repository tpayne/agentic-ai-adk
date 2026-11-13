"""TOGAF architecture-artifact JSON persistence + lightweight structural
validation. TOGAF-schema counterpart to design_json.py -- same save/load/
template-fallback shape, validating against the structural essentials
(document_metadata's required fields, the same requirement id/acceptance-
criteria cross-field check design_json.py already has) rather than a full
JSON-Schema document.

Scope (deliberate, not exhaustive TOGAF coverage -- see registries/
togaf.hocon's own header comment for the full reasoning): ADM Phase A
(architecture_vision), a dedicated Architecture Requirements Specification,
a bounded Architecture Principles set (Preliminary Phase equivalent), Phase
B (business_architecture, intentionally light), Phase C
(data_architecture + application_architecture), Phase D
(technology_architecture), Phase E (opportunities_and_solutions), a LIGHT
Phase F (migration_planning -- deliberately no date/budget/team-capacity
fields anywhere in this schema, the same "enforced by absence" anti-
fabrication discipline design_json.py's own architecture_decisions already
uses for its missing status/date fields), and a LIGHT Phase G
(architecture_compliance_assessment, referencing the design's own already-
real compliance_and_standards/risk_register rather than fabricating new
governance structures). Phase H (Architecture Change Management) and full
Preliminary-phase capability-maturity assessment are OUT OF SCOPE -- both
are ongoing governance practices, not point-in-time document artifacts a
generator can produce.

Unlike design_json.py's document_type ("HLD"/"LLD"/"Combined"), there is NO
document_type field here -- the Architecture Vision Document vs.
Architecture Definition Document split is a render-time togaf_variant
argument (see docgen/generation.py's _resolve_togaf_variant), not persisted
content; both documents render from the SAME JSON object every time.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.TogafJson")

TOGAF_JSON_FILENAME = "togaf_data.json"

# One-item example shapes (not bare `{}`/`[]`) so the generating agent
# lands on real key names -- same reasoning as DESIGN_TEMPLATE's own
# header comment.
TOGAF_TEMPLATE: Dict[str, Any] = {
    "document_metadata": {
        "document_id": "",
        "system_name": "",
        "title": "",
        "version": "1.0",
        "status": "draft",
    },

    # ---- ARCHITECTURE VISION DOCUMENT CONTENT ----
    "architecture_vision": {
        "problem_statement": "",
        "vision_statement": "",
        "business_goals": [],
        "business_drivers": [],
        "stakeholders": [{"name": "", "role": "", "concerns": []}],
        "scope": {"in_scope": [], "out_of_scope": [], "constraints": [], "assumptions": []},
        # cross-refs ids from architecture_requirements_specification below
        "key_business_requirements": [],
        "risks_and_mitigations": [{"id": "", "description": "", "mitigation": ""}],
    },
    "architecture_requirements_specification": {
        "functional_requirements": [
            {"id": "", "description": "", "priority": "", "source": "", "acceptance_criteria": []}
        ],
        "non_functional_requirements": [
            {"id": "", "characteristic": "", "description": "", "target": "", "source": ""}
        ],
        "constraints": [],
        "assumptions": [],
        # requirement_id -> the capability/component id(s) that satisfy it --
        # the backbone of the traceability chain TOGAF_Compliance_Agent's
        # own checklist audits (business driver -> capability ->
        # application/data/technology component -> requirement id).
        "traceability_matrix": [{"requirement_id": "", "satisfied_by": []}],
    },
    # Bounded Preliminary-phase equivalent -- generic principles grounded
    # in the real stated constraints, not invented ceremony.
    "architecture_principles": [
        {"id": "PRIN-001", "name": "", "statement": "", "rationale": "", "implications": []}
    ],

    # ---- ARCHITECTURE DEFINITION DOCUMENT CONTENT ----
    "business_architecture": {
        "capabilities": [
            {"id": "", "name": "", "description": "", "supports_goals": [], "owner": ""}
        ],
        "capability_map_diagram": {
            "diagram_id": "", "diagram_type": "node_grid", "title": "", "description": "",
        },
        "value_streams": [{"name": "", "description": "", "stages": []}],
    },
    "data_architecture": {
        "data_entities": [
            {"name": "", "description": "", "owner": "", "attributes": [], "classification": ""}
        ],
        "data_flows": [{"source": "", "target": "", "description": "", "data_entities": []}],
        "data_flow_diagram": {
            "diagram_id": "", "diagram_type": "edge_graph", "title": "", "description": "",
        },
        # Pulled from design's low_level_design.database_design when
        # present -- not re-derived/re-authored, per the project-wide
        # "design takes precedence, don't re-reason" rule.
        "database_design_ref": [],
    },
    "application_architecture": {
        "application_components": [
            {
                "name": "", "description": "", "realizes_capabilities": [],
                "satisfies_requirements": [],
            }
        ],
        # Shaped to match generate_uml_diagram's existing edge-graph branch
        # (labeled source/target pairs) -- deliberately NOT reusing design's
        # own "integration_points" key name, since this is a different
        # domain object even though the shape is similar.
        "application_communications": [{"source": "", "target": "", "protocol": "", "description": ""}],
        "application_communication_diagram": {
            "diagram_id": "", "diagram_type": "edge_graph", "title": "", "description": "",
        },
    },
    "technology_architecture": {
        "technology_portfolio": [
            {"category": "", "technology": "", "version": "", "justification": ""}
        ],
        "technology_portfolio_diagram": {
            "diagram_id": "", "diagram_type": "node_grid", "title": "", "description": "",
        },
        # Pulled from design's deployment_topology -- not re-authored.
        "deployment_topology_ref": [],
    },
    # Every gap MUST cite a real requirement/design id in "grounded_in" --
    # never invent a gap with no grounding.
    "opportunities_and_solutions": [
        {
            "id": "", "gap_description": "", "grounded_in": [],
            "proposed_solution": "", "work_package_ref": "",
        }
    ],
    # LIGHT, dependency-sequenced only -- deliberately NO date/budget/
    # team-capacity field anywhere in this object (enforced by absence,
    # not by an instruction not to fill one in -- the same discipline
    # design_json.py's own architecture_decisions uses for its missing
    # status/date fields).
    "migration_planning": {
        "work_packages": [
            {"id": "", "name": "", "description": "", "depends_on": [], "delivers": []}
        ],
        "sequencing_notes": "",
    },
    # LIGHT -- references design's own already-real compliance_and_
    # standards/risk_register by id; never fabricates new governance
    # structures.
    "architecture_compliance_assessment": {
        "compliance_findings": [
            {"standard_or_requirement": "", "status": "", "reference": ""}
        ],
    },

    "glossary_and_references": {
        "glossary": [{"term": "", "definition": ""}],
        "references": [{"title": "", "source": "", "url": ""}],
    },
    "appendix": {},
}


def load_togaf_template() -> Dict[str, Any]:
    return json.loads(json.dumps(TOGAF_TEMPLATE))


def load_master_togaf_json() -> Dict[str, Any]:
    """Returns the existing baseline if present, else the empty template --
    ALWAYS returns a valid JSON object, the generator never needs to
    construct one from scratch."""
    path = paths.output_path(TOGAF_JSON_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.debug("Loaded existing TOGAF baseline from %s.", path)
            return data
        except Exception:
            logger.exception(
                "Existing TOGAF baseline at %s exists but could not be read -- falling back to the "
                "empty template. Any un-persisted work in that file is NOT reflected in what gets returned.",
                path,
            )
    else:
        logger.debug("No TOGAF baseline at %s -- falling back to the empty template.", path)
    return load_togaf_template()


def load_full_togaf_context() -> Dict[str, Any]:
    """Same content as load_master_togaf_json -- kept as a separate name
    for the scenario-tester agent."""
    return load_master_togaf_json()


def validate_togaf_json(json_content: Any) -> Dict[str, Any]:
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

    ars = json_content.get("architecture_requirements_specification")
    if isinstance(ars, dict):
        for requirement_type in ("functional_requirements", "non_functional_requirements"):
            items = ars.get(requirement_type)
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                if not str(item.get("id") or "").strip():
                    issues.append({
                        "location": f"architecture_requirements_specification.{requirement_type}[{index}].id",
                        "issue": "A stable identifier is required, e.g. 'FR-001' or 'NFR-001'",
                    })

    return {"valid": len(issues) == 0, "issues": issues}


def persist_final_togaf_json(json_content: Any) -> str:
    if not json_content or (isinstance(json_content, dict) and len(json_content) == 0):
        logger.debug("persist_final_togaf_json called with no content -- nothing to do.")
        return "INFO: No JSON content provided, so nothing has been done."

    if isinstance(json_content, str):
        try:
            json_content = json.loads(json_content)
        except Exception as e:
            logger.warning("persist_final_togaf_json received a string that is not valid JSON: %s", e)
            return f"ERROR: Could not parse JSON content: {e}"

    validation = validate_togaf_json(json_content)
    if not validation["valid"]:
        # INFO, not WARNING -- same reasoning as design_json.py's own
        # persist_final_design_json: this fires on routine mid-process
        # validate-and-retry attempts, not just a final failure, and
        # stays fully captured in the log file either way.
        logger.info("TOGAF_Agent's TOGAF JSON failed validation, nothing persisted: %s", validation["issues"])
        return f"ERROR: JSON failed validation: {validation['issues']}"

    path = paths.output_path(TOGAF_JSON_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(json_content, f, indent=2, ensure_ascii=False)
        logger.info("Persisted TOGAF JSON to %s.", path)
        return f"SUCCESS: The file {path} was saved successfully."
    except Exception as e:
        logger.exception("Failed to write TOGAF JSON to %s.", path)
        return f"ERROR: Could not save TOGAF JSON: {e}"


def extract_valid_json(raw: str) -> Optional[Dict[str, Any]]:
    """Brace-balanced JSON object extractor for a possibly-noisy LLM
    string -- identical algorithm to design_json.py's/process_json.py's
    own extract_valid_json."""
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
