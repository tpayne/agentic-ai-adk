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

# Field shapes match design_document_schema.json's own $defs verbatim -- an
# empty `{}`/`[]` with no structural hint, as this dict originally had for
# every nested field, left Design_Doc_Agent with nothing but loosely-worded
# prose instructions to infer a shape from. Confirmed directly against a
# real generated document: the model invented divergent, inconsistent
# shapes field-by-field -- "context_statement" instead of business_context's
# own "purpose", "strategic_objectives" instead of "objectives",
# "hld_component_name" instead of low_level_design.components[]'s own
# "component_name", "risk_description"/"probability"/"mitigation_strategy"
# instead of risk_register's own "description"/"likelihood"/"mitigation",
# three entirely different non-schema keys for compliance_and_standards
# ("standards_alignment"/"regulatory_frameworks"/"compliance_requirements"),
# a DICT-of-categories instead of governance_requirements'/
# continuous_improvement's own flat-list shapes, and a bare STRING instead
# of an ARRAY for architecture_analysis's strengths/weaknesses/risks. None
# of that was silently harmless -- compliance_and_standards' entire section
# rendered nothing at all, and high_level_design's own rich content
# (security/scalability/availability/risks) had no bespoke renderer
# checking for it in the first place. One-item example shapes restore the
# schema's own key names and types so a fresh generation naturally lands on
# what doc_design_sections.py's renderers actually expect; those renderers
# were separately hardened (see coded_tools/common/docgen/) to also
# tolerate the divergent shapes already observed, so a document generated
# under the old empty-`{}` template improves too, without needing to
# regenerate.
DESIGN_TEMPLATE: Dict[str, Any] = {
    "document_metadata": {
        "document_id": "",
        "document_type": "",
        "system_name": "",
        "title": "",
        "version": "1.0",
        "status": "draft",
    },
    "business_context": {
        "purpose": "",
        "scope": "",
        "objectives": [],
        "business_drivers": [],
        "assumptions": [],
        "constraints": [],
    },
    "architecture_description": {
        "stakeholders": [{"stakeholder_name": "", "role": "", "concerns": [], "responsibilities": []}],
        "concerns": [],
        "viewpoints": [
            {
                "viewpoint_name": "", "description": "", "stakeholders_addressed": [],
                "concerns_addressed": [], "modeling_conventions": "", "applicable_standard": "",
            }
        ],
        "views": [{"view_name": "", "viewpoint_ref": "", "description": "", "diagrams": [], "elements": []}],
        "architecture_analysis": [
            {
                "title": "",
                "description": "",
                "strengths": [],
                "weaknesses": [],
                "risks": [],
                "alternatives": [],
                "recommendation": "",
            }
        ],
    },
    "requirements": {
        "functional_requirements": [
            {"id": "", "description": "", "priority": "", "source": "", "acceptance_criteria": [], "status": ""}
        ],
        "non_functional_requirements": [
            {
                "id": "", "characteristic": "", "sub_characteristic": "", "description": "",
                "metric": "", "target": "", "measurement_method": "", "priority": "",
                "acceptance_criteria": [],
            }
        ],
    },
    "system_context": {
        "actors": [{"name": "", "type": "", "description": ""}],
        "external_systems": [{"name": "", "description": "", "interface_type": "", "data_exchanged": "", "owner": ""}],
        "context_diagram": {
            "diagram_id": "", "diagram_type": "context", "notation_standard": "", "title": "", "description": "",
        },
    },
    "high_level_design": {
        "solution_overview": "",
        "architecture_style": "",
        "components": [
            {
                "component_name": "", "description": "", "dependencies": [], "type": "",
                "technology_stack": [], "interfaces": [], "owner": "",
            }
        ],
        "integration_points": [{"source": "", "target": "", "integration_pattern": "", "protocol": "", "description": ""}],
        "data_flow_overview": "",
        "technology_stack": [{"category": "", "technology": "", "version": "", "justification": "", "license": ""}],
        "deployment_topology": {
            "environments": [{"name": "", "description": "", "infrastructure": ""}],
            "diagram": {"diagram_id": "", "diagram_type": "deployment", "notation_standard": "", "title": "", "description": ""},
        },
        "security_architecture": {
            "authentication_mechanism": "", "authorization_model": "",
            "data_protection_measures": [], "threat_model_reference": "",
        },
        "scalability_and_performance": {"expected_load": "", "scaling_strategy": "", "performance_targets": []},
        "availability_and_resilience": {
            "availability_target": "", "redundancy_strategy": "",
            "disaster_recovery_plan": "", "backup_strategy": "", "rto": "", "rpo": "",
        },
        "risks_and_mitigations": [
            {"id": "", "description": "", "category": "", "likelihood": "", "impact": "", "mitigation": "", "owner": "", "status": ""}
        ],
    },
    # "sequence_flows"/"class_design" specifically are what let
    # _render_diagram_descriptor -> generate_uml_diagram actually draw a
    # real UML sequence/class diagram instead of a "[Diagram not yet
    # generated]" placeholder note -- confirmed directly: a real generated
    # design document with no low_level_design shape hint at all produced
    # zero sequence_flows/class_design/interface_contracts anywhere, so
    # the entire "Runtime Processing and Sequence Flows" subsection never
    # had anything to render, even though the renderer fully supports it.
    "low_level_design": {
        "components": [
            {
                "component_name": "", "description": "", "responsibilities": [],
                "configuration_parameters": [{"name": "", "type": "", "default_value": "", "description": ""}],
                "api_specifications": [
                    {
                        "interface_name": "", "protocol": "REST", "contract_reference": "",
                        "request_schema": "", "response_schema": "", "authentication": "",
                        "versioning_strategy": "", "error_handling": "",
                    }
                ],
                "sequence_flows": [
                    {
                        "diagram_id": "", "diagram_type": "sequence", "notation_standard": "UML",
                        "title": "", "description": "",
                        "participants": ["", ""],
                        "steps": [
                            {
                                "step_number": 1, "from_participant": "", "to_participant": "",
                                "message": "", "is_async": False, "is_return": False, "notes": "",
                            }
                        ],
                    }
                ],
                "class_design": {
                    "classes": [{"class_name": "", "attributes": [], "methods": [], "design_patterns_used": []}],
                },
                "logging_and_monitoring": {"log_levels": [], "monitored_metrics": [], "alerting_rules": []},
                "algorithm_details": "",
                "error_handling_strategy": "",
                "unit_test_strategy": "",
            }
        ],
        "database_design": [
            {
                "schema_name": "", "database_technology": "",
                "entities": [{"entity_name": "", "attributes": [{"name": "", "type": "", "constraints": [], "description": ""}]}],
                "indexes": [], "partitioning_strategy": "",
            }
        ],
        "interface_contracts": [
            {
                "interface_name": "", "protocol": "REST", "contract_reference": "",
                "authentication": "", "versioning_strategy": "", "error_handling": "",
            }
        ],
        "detailed_sequence_flows": [
            {
                "diagram_id": "", "diagram_type": "sequence", "notation_standard": "UML",
                "title": "", "description": "", "participants": ["", ""],
                "steps": [
                    {
                        "step_number": 1, "from_participant": "", "to_participant": "",
                        "message": "", "is_async": False, "is_return": False, "notes": "",
                    }
                ],
            }
        ],
        "exception_handling_strategy": "",
    },
    "quality_attributes": [
        {"characteristic": "", "sub_characteristic": "", "description": "", "metric": "", "target": "", "measurement_method": ""}
    ],
    "compliance_and_standards": {
        "applicable_standards": [
            {"standard_name": "", "standard_body": "", "clause_reference": "", "applicability": "", "compliance_status": ""}
        ],
        "regulatory_requirements": [
            {"regulation_name": "", "jurisdiction": "", "requirement_description": "", "compliance_status": ""}
        ],
    },
    "risk_register": [
        {"id": "", "description": "", "category": "", "likelihood": "", "impact": "", "mitigation": "", "owner": "", "status": ""}
    ],
    "governance_requirements": [],
    "continuous_improvement": [{"review_frequency": "", "improvement_inputs": []}],
    "glossary_and_references": {
        "glossary": [{"term": "", "definition": ""}],
        "references": [{"title": "", "source": "", "url": "", "version": ""}],
    },
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

    requirements = json_content.get("requirements")
    if isinstance(requirements, dict):
        for requirement_type in ("functional_requirements", "non_functional_requirements"):
            items = requirements.get(requirement_type)
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                criteria = item.get("acceptance_criteria")
                if not isinstance(criteria, list) or not any(
                    isinstance(criterion, str) and criterion.strip() for criterion in criteria
                ):
                    issues.append({
                        "location": f"requirements.{requirement_type}[{index}].acceptance_criteria",
                        "issue": "At least one concrete, verifiable acceptance criterion is required",
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
