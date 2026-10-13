"""Exercises the design-document generation stage end-to-end against the
real CodedTool classes, mirroring tests/test_docgen.py's process-schema
coverage. The isolated_output_dir autouse fixture (conftest.py) means every
assertion here reads/writes only a throwaway tmp_path.
"""

import copy
import json
import os

import docx

from coded_tools.common import paths
from process_toolkit.schema.process_json import DESIGN_JSON_FILENAME
from process_toolkit.docgen.edge_inference import generate_clean_diagram
from process_toolkit.docgen.generation import create_standard_doc_from_file
from coded_tools.design.edge_inference_tool import GenerateDesignFlowDiagramCodedTool
from coded_tools.design.doc_generation_tool import GenerateDesignDocumentCodedTool

SAMPLE_DESIGN = {
    "document_metadata": {
        "document_id": "DOC-1", "document_type": "Combined", "system_name": "Checkout",
        "title": "Checkout Combined Design", "version": "1.0", "status": "draft",
        "industry_sector": "Retail",
    },
    "business_context": {
        "purpose": "Modernize checkout.", "scope": "Checkout flow only.",
        "objectives": ["Reduce latency"], "assumptions": ["Traffic grows 2x"],
        "constraints": ["Must use existing payment gateway"],
    },
    "architecture_description": {
        "stakeholders": [{"stakeholder_name": "Eng Lead", "role": "Owner", "responsibilities": ["Approve design"]}],
        "architecture_analysis": [{
            "title": "Microservices vs Monolith", "description": "Chosen microservices.",
            "strengths": ["Scalable"], "weaknesses": ["Complex"],
            "recommendation": "Proceed with microservices.",
        }],
    },
    "requirements": {
        "functional_requirements": [{
            "id": "FR-001", "priority": "high", "description": "Support credit card payment",
            "acceptance_criteria": ["Visa/MC accepted"],
        }],
    },
    "system_context": {
        "actors": [{"name": "Shopper", "type": "human", "description": "End user"}],
        "external_systems": [{"name": "Payment Gateway", "description": "3rd party"}],
    },
    "high_level_design": {
        "components": [
            {"component_name": "API Gateway", "description": "Entry point", "dependencies": []},
            {"component_name": "Checkout Service", "description": "Core logic", "dependencies": ["API Gateway"]},
        ],
        "integration_points": [{"source": "Checkout Service", "target": "API Gateway", "protocol": "REST"}],
        "availability_and_resilience": {"availability_target": "99.9%"},
    },
    "low_level_design": {
        "components": [{"component_name": "Checkout Service", "description": "Impl detail", "responsibilities": ["Validate cart"]}],
        "exception_handling_strategy": "Retries with backoff.",
    },
    "quality_attributes": [{
        "characteristic": "performance_efficiency", "description": "Fast checkout",
        "metric": "P95 latency", "target": "<200ms",
    }],
    "compliance_and_standards": {"applicable_standards": [{"standard_name": "PCI DSS", "compliance_status": "compliant"}]},
    "risk_register": [{
        "id": "R1", "category": "Security", "likelihood": "medium", "impact": "high",
        "description": "Card data exposure", "mitigation": "Tokenization",
    }],
    "governance_requirements": ["Quarterly security review"],
    "glossary_and_references": {"glossary": [{"term": "PCI DSS", "definition": "Payment Card Industry Data Security Standard"}]},
}


def _write_sample_design_json(design=None):
    with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(SAMPLE_DESIGN if design is None else design, f)


def test_generate_clean_diagram_produces_a_png_for_a_design_document():
    _write_sample_design_json()

    result = generate_clean_diagram()

    assert "Diagram successfully generated at" in result
    assert os.path.exists(os.path.join(paths.OUTPUT_DIR, "checkout_combined_design_flow.png"))


def test_flowchart_section_finds_the_generic_fallback_diagram_name():
    """Regression test for a real crash: generate_clean_diagram() names its
    OWN output after document_metadata.title/system_name -- but falls back
    to the literal "design" (-> design_flow.png) when it can't load a
    valid design document at that moment (e.g. output/design_data.json is
    empty/invalid right then -- observed in a real run mid "repair"). The
    document-building side used to independently GUESS the diagram's
    filename from `process_name` instead of using the path
    generate_clean_diagram() actually reported, and its last-resort guess
    was hardcoded to "process_flow.png" -- never matching "design_flow.png"
    for this exact fallback case -- so the whole document generation
    crashed with "image is missing" despite the diagram having genuinely
    been generated successfully, just under a different name.
    """
    # "{}" is a present-but-invalid design document -- isinstance(data, dict)
    # is true but `not data` is ALSO true for an empty dict, which is
    # exactly what _infer_edges_from_design_json's own "no valid design
    # document JSON" branch checks for. detect_schema_type_from_disk()
    # still resolves to "design" because the file exists.
    with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
        f.write("{}")

    from process_toolkit.docgen.technical import _add_flowchart_section

    doc = docx.Document()
    # Deliberately a process_name that won't match "design" (the generic
    # fallback stem) -- the real crash's own process_name didn't match it
    # either.
    rendered = _add_flowchart_section(
        doc, "Secure RDS", heading="6.0 Architecture Flow Diagram", generate_diagram=True,
    )

    assert rendered is True
    assert os.path.isfile(os.path.join(paths.OUTPUT_DIR, "design_flow.png"))
    assert len(doc.inline_shapes) == 1


def test_infer_edges_accepts_source_component_target_component_as_a_fallback():
    """Regression test for a real generated document: the design agent has
    been observed emitting "source_component"/"target_component" instead of
    the schema-correct "source"/"target" (design.hocon's "EXACT FIELD
    SHAPES" now calls this out explicitly) -- _infer_edges_from_design_json
    must still pick up that edge rather than silently dropping it, which
    would otherwise leave the architecture diagram missing a real,
    documented integration.

    Imports the private helper directly (no precedent elsewhere in this
    test file, which otherwise tests only through the public
    generate_clean_diagram/create_standard_doc_from_file entry points) --
    this is a pure, side-effect-free function, and asserting that ONE
    specific edge is present isn't practically checkable from the
    rendered PNG the public API produces.
    """
    from process_toolkit.docgen.edge_inference import _infer_edges_from_design_json

    design = copy.deepcopy(SAMPLE_DESIGN)
    # Deliberately NO dependency link between these two -- the integration_
    # points entry below (using the wrong-but-observed key names) is the
    # ONLY thing that should connect them.
    design["high_level_design"]["components"] = [
        {"component_name": "API Gateway", "description": "Entry point", "dependencies": []},
        {"component_name": "Checkout Service", "description": "Core logic", "dependencies": []},
    ]
    design["high_level_design"]["integration_points"] = [
        {"source_component": "Checkout Service", "target_component": "API Gateway", "protocol": "REST"},
    ]
    _write_sample_design_json(design)

    _doc_name, edges, _lane_map, _label_map = _infer_edges_from_design_json()

    assert ("Checkout Service", "API Gateway") in edges


def test_create_standard_doc_from_file_builds_a_real_design_docx_with_expected_sections():
    _write_sample_design_json()

    result = create_standard_doc_from_file("Checkout", schema_type="design")

    assert result.startswith("SUCCESS:")
    out_path = os.path.join(paths.OUTPUT_DIR, "Checkout_Combined_Design.docx")
    assert os.path.exists(out_path)

    doc = docx.Document(out_path)
    assert len(doc.inline_shapes) == 1
    assert os.path.isfile(os.path.join(paths.OUTPUT_DIR, "checkout_combined_design_flow.png"))
    heading_texts = [
        p.text for p in doc.paragraphs
        if p.style is not None and p.style.name == "Heading 1"
    ]
    assert "1.0 Executive Summary" in heading_texts
    assert "2.0 Stakeholders and Responsibilities" in heading_texts
    assert "3.0 Requirements" in heading_texts
    assert "4.0 System Context" in heading_texts
    assert "5.0 Architecture Description" in heading_texts
    assert any(h.endswith("Low-Level Design") for h in heading_texts)
    assert any(h.endswith("Glossary and References") for h in heading_texts)


def test_design_document_renders_existing_prose_sequence_flows_as_images():
    design = copy.deepcopy(SAMPLE_DESIGN)
    design["low_level_design"]["components"][0]["sequence_flows"] = [
        {
            "title": "Backup Execution",
            "diagram_id": "backup-execution",
            "diagram_type": "sequence",
            "steps": [
                "The backup service starts a scheduled job.",
                "The job stores an encrypted recovery point.",
            ],
        },
    ]
    _write_sample_design_json(design)

    result = create_standard_doc_from_file("Checkout", schema_type="design")

    assert result.startswith("SUCCESS:")
    doc = docx.Document(os.path.join(paths.OUTPUT_DIR, "Checkout_Combined_Design.docx"))
    assert len(doc.inline_shapes) == 2
    assert os.path.isfile(os.path.join(paths.OUTPUT_DIR, "uml_diagrams", "backup-execution.png"))


def test_sequence_flow_using_legacy_name_key_gets_a_descriptive_filename_and_heading():
    """Regression test for a real generated document: a flow with neither
    "title" nor "diagram_id" (only the legacy "name" key -- exactly what
    the AWS backup/governance design doc that surfaced this had) used to
    fall all the way through to the bare literal filename "diagram.png"
    and heading "Diagram". Both should now be built from "name" instead.
    """
    design = copy.deepcopy(SAMPLE_DESIGN)
    design["low_level_design"]["components"][0]["sequence_flows"] = [
        {
            "name": "Centralized Backup Execution",
            "steps": [
                "AWS Backup triggers a job based on schedule and tags.",
                "Data is encrypted and copied to the central vault.",
            ],
        },
    ]
    _write_sample_design_json(design)

    result = create_standard_doc_from_file("Checkout", schema_type="design")

    assert result.startswith("SUCCESS:")
    assert os.path.isfile(
        os.path.join(paths.OUTPUT_DIR, "uml_diagrams", "centralized_backup_execution.png")
    )
    assert not os.path.isfile(os.path.join(paths.OUTPUT_DIR, "uml_diagrams", "diagram.png"))

    doc = docx.Document(os.path.join(paths.OUTPUT_DIR, "Checkout_Combined_Design.docx"))
    heading_texts = [p.text for p in doc.paragraphs if p.style is not None and p.style.name == "Heading 3"]
    assert "Centralized Backup Execution" in heading_texts
    assert "Diagram" not in heading_texts


def test_two_untitled_unnamed_flows_on_different_components_do_not_collide():
    """Even with NEITHER "title"/"diagram_id" NOR "name" -- the fully
    generic case -- two different components' flows must not silently
    overwrite one another's image file."""
    design = copy.deepcopy(SAMPLE_DESIGN)
    design["low_level_design"]["components"] = [
        {
            "component_name": "Checkout Service", "description": "Impl detail",
            "sequence_flows": [{"steps": ["Validate the cart.", "Reserve inventory."]}],
        },
        {
            "component_name": "Payment Service", "description": "Impl detail",
            "sequence_flows": [{"steps": ["Charge the card.", "Record the receipt."]}],
        },
    ]
    _write_sample_design_json(design)

    result = create_standard_doc_from_file("Checkout", schema_type="design")

    assert result.startswith("SUCCESS:")
    uml_dir = os.path.join(paths.OUTPUT_DIR, "uml_diagrams")
    assert os.path.isfile(os.path.join(uml_dir, "checkout_service-diagram.png"))
    assert os.path.isfile(os.path.join(uml_dir, "payment_service-diagram.png"))

    doc = docx.Document(os.path.join(paths.OUTPUT_DIR, "Checkout_Combined_Design.docx"))
    assert len(doc.inline_shapes) == 3  # flow diagram + one per component's sequence diagram


def test_design_document_preserves_context_roles_and_stakeholder_concerns():
    design = copy.deepcopy(SAMPLE_DESIGN)
    design["system_context"]["actors"] = [{"name": "Cloud Admin", "role": "Manages platform accounts."}]
    design["architecture_description"]["stakeholders"] = [
        {"name": "Security Team", "role": "Owns governance.", "concerns": ["Tenant isolation"]},
    ]
    _write_sample_design_json(design)

    result = create_standard_doc_from_file("Checkout", schema_type="design")

    assert result.startswith("SUCCESS:")
    doc = docx.Document(os.path.join(paths.OUTPUT_DIR, "Checkout_Combined_Design.docx"))
    cells = [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    assert "Manages platform accounts." in cells
    stakeholder_details = next(cell for cell in cells if "Concerns:" in cell)
    assert "Owns governance." in stakeholder_details
    assert "Concerns: Tenant isolation" in stakeholder_details


def test_generate_design_flow_diagram_coded_tool_invoke():
    _write_sample_design_json()
    tool = GenerateDesignFlowDiagramCodedTool()
    result = tool.invoke({}, {})
    assert "Diagram successfully generated at" in result


def test_generate_design_document_coded_tool_invoke():
    _write_sample_design_json()
    tool = GenerateDesignDocumentCodedTool()
    result = tool.invoke({}, {})
    assert result.startswith("SUCCESS:")
    assert os.path.exists(os.path.join(paths.OUTPUT_DIR, "Checkout_Combined_Design.docx"))


def test_create_standard_doc_from_file_auto_detects_design_schema_from_disk():
    # No explicit schema_type passed -- detect_schema_type_from_disk must
    # resolve to "design" since design_data.json exists and
    # process_data.json does not.
    _write_sample_design_json()
    result = create_standard_doc_from_file("Checkout")
    assert result.startswith("SUCCESS:")


# ============================================================
# Real-world field shape regressions.
#
# A live LLM run against this schema produced a document described by the
# user as "totally screwed": a real design covering an AWS RDS/Aurora
# architecture. Field-by-field comparison against the real design_data.json
# found a live model consistently diverging from design_document_schema.json
# in ways SAMPLE_DESIGN above never exercises -- "context_statement"/
# "strategic_objectives" instead of business_context's own "purpose"/
# "objectives", "hld_component_name" instead of low_level_design's own
# "component_name", a bare STRING instead of an ARRAY for
# architecture_analysis's strengths/weaknesses/risks (silently exploded
# into one bullet per CHARACTER -- python's `for v in "High availability"`
# iterates characters, each of which passes an `isinstance(v, str)` filter),
# "risk_description"/"probability"/"mitigation_strategy" instead of
# risk_register's own "description"/"likelihood"/"mitigation", three
# different non-schema keys for compliance_and_standards (entirely
# unrecognized, so the whole section rendered nothing at all), a DICT
# grouping requirements/practices by category instead of
# governance_requirements'/continuous_improvement's own flat-list shape
# (`for item in a_dict` iterates its KEYS, so the bullets rendered were the
# literal category names), a nested "metrics" list instead of flat
# metric/target fields on each quality_attributes entry, and
# high_level_design's own rich content (security_architecture,
# scalability_and_performance, availability_and_resilience,
# risks_and_mitigations, integration_points) having no renderer at all
# checking for it -- extracted into consumed_keys (to suppress it from
# Appendix B) but never actually displayed anywhere in the document body.
# This test pins down the real-world shape directly so none of it can
# regress.
# ============================================================

REAL_WORLD_DESIGN = {
    "document_metadata": {
        "document_id": "ARCH-RDS-001", "document_type": "Combined", "system_name": "Secure RDS Architecture",
        "title": "Secure AWS RDS Design", "version": "1.1", "status": "draft",
        "industry_sector": "Information Technology",
    },
    "business_context": {
        "context_statement": "The system provides a secure, managed relational database environment on AWS.",
        "business_drivers": ["Data security compliance requirements."],
        "strategic_objectives": ["Reduce database management overhead."],
    },
    "architecture_description": {
        "stakeholders": [{"name": "Security Engineers", "role": "Ensure encryption compliance."}],
        "architecture_analysis": [{
            "description": "Utilizing Amazon Aurora in a Multi-AZ configuration.",
            "strengths": "High availability, automated patching, and storage auto-scaling.",
            "weaknesses": "Aurora has a higher entry cost compared to small RDS instances.",
            "risks": "Configuration drift in Security Groups or IAM policies.",
            "recommendation": "Proceed with Amazon Aurora Multi-AZ.",
        }],
    },
    "requirements": {
        "functional_requirements": [{"id": "FR-001", "priority": "critical", "description": "Provision Aurora."}],
    },
    "high_level_design": {
        "components": [
            {"component_name": "Amazon Aurora Cluster", "type": "Database", "description": "Managed DB cluster.", "dependencies": []},
        ],
        "integration_points": [
            {"id": "INT-001", "source_component": "ALB", "target_component": "App Tier", "interface_type": "HTTPS", "description": "Routes traffic."},
        ],
        "security_architecture": {"infrastructure_security": "Security Groups enforcing least privilege."},
        "scalability_and_performance": {"description": "Elastic scaling via Aurora storage auto-scaling."},
        "availability_and_resilience": {"availability_target": "99.95%", "description": "Multi-AZ failover."},
        "risks_and_mitigations": [{"risk": "Credential Exposure", "impact": "High", "probability": "Low", "mitigation": "Use Secrets Manager."}],
    },
    "low_level_design": {
        "components": [
            {"hld_component_name": "Amazon Aurora Cluster", "responsibilities": ["Persistent data storage"]},
        ],
    },
    "quality_attributes": [
        {"characteristic": "Security", "description": "Protection of data.", "metrics": [
            {"metric": "Encryption Coverage", "target": "100% of data volumes"},
            {"metric": "Vulnerability Remediation", "target": "Within 24 hours"},
        ]},
    ],
    "compliance_and_standards": {
        "regulatory_frameworks": [{"name": "DPP-2024", "description": "Internal Data Protection Policy."}],
        "standards_alignment": [{"standard": "AWS WAF-S", "description": "Well-Architected Security Pillar."}],
    },
    "risk_register": [{
        "risk_description": "Unauthorized network access to the database.", "impact": "High",
        "probability": "Medium", "mitigation_strategy": "Strict Security Group rules.",
        "owner": "Security Team", "status": "open",
    }],
    "governance_requirements": {
        "policy_framework": [{"description": "IAM policies enforcing least privilege."}],
        "data_governance": [{"description": "Data classification policies."}],
    },
    "continuous_improvement": {
        "feedback_mechanisms": ["Quarterly architectural reviews."],
        "monitoring_and_logging": ["CloudWatch metrics."],
    },
}


def _write_real_world_design_json():
    with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(REAL_WORLD_DESIGN, f)


def _all_table_rows(doc):
    return [[c.text for c in row.cells] for table in doc.tables for row in table.rows]


def test_real_world_design_doc_handles_every_observed_field_divergence():
    _write_real_world_design_json()

    result = create_standard_doc_from_file("Secure RDS", schema_type="design")
    assert result.startswith("SUCCESS:")

    out_path = os.path.join(paths.OUTPUT_DIR, "Secure_AWS_RDS_Design.docx")
    doc = docx.Document(out_path)

    body_text = "\n".join(p.text for p in doc.paragraphs)
    flat_cells = [cell for row in _all_table_rows(doc) for cell in row]

    # business_context: context_statement/strategic_objectives recovered.
    assert "The system provides a secure, managed relational database environment on AWS." in body_text
    assert "Reduce database management overhead." in body_text

    # architecture_analysis: strengths/weaknesses/risks given as plain
    # strings render as ONE bullet each, not one bullet per character --
    # check exact paragraph text, since a substring check would also
    # (correctly) match inside the real, full-sentence bullet below.
    assert "High availability, automated patching, and storage auto-scaling." in body_text
    paragraph_texts = [p.text for p in doc.paragraphs]
    assert "• H" not in paragraph_texts
    assert "• i" not in paragraph_texts

    # high_level_design's rich content now appears somewhere in the body.
    assert "Security Groups enforcing least privilege." in body_text
    assert "Elastic scaling via Aurora storage auto-scaling." in body_text
    assert "Multi-AZ failover." in body_text
    assert "Routes traffic." in body_text
    assert "Credential Exposure" in flat_cells or "Credential Exposure" in body_text

    # low_level_design: hld_component_name recognized as the component name.
    assert "Amazon Aurora Cluster" in flat_cells or "Amazon Aurora Cluster" in body_text

    # quality_attributes: nested "metrics" list produces real Metric/Target
    # cells, one row per metric.
    assert "Encryption Coverage" in flat_cells
    assert "100% of data volumes" in flat_cells
    assert "Vulnerability Remediation" in flat_cells

    # compliance_and_standards: alternate keys recognized, section renders
    # instead of being silently skipped entirely.
    assert "DPP-2024" in flat_cells
    assert "AWS WAF-S" in flat_cells

    # risk_register: synonym keys recovered (description/mitigation cells
    # go through _set_cell_bullets, which prefixes "• "), Owner/Status
    # columns present.
    assert "• Unauthorized network access to the database." in flat_cells
    assert "• Strict Security Group rules." in flat_cells
    assert "Security Team" in flat_cells
    assert "Open" in flat_cells

    # governance_requirements/continuous_improvement: dict-of-categories
    # renders real content, not the bare category key names as bullets.
    assert "IAM policies enforcing least privilege." in body_text
    assert "Quarterly architectural reviews." in body_text
    assert "Policy Framework" in body_text
    assert "Feedback Mechanisms" in body_text


def test_low_level_design_sequence_flow_renders_a_real_uml_diagram():
    # DESIGN_TEMPLATE originally hinted only low_level_design.components'
    # name/description/responsibilities/configuration_parameters -- never
    # "sequence_flows", the field _render_diagram_descriptor ->
    # generate_uml_diagram needs to draw a real UML sequence diagram
    # instead of a "[Sequence not yet generated]" placeholder note.
    # Confirmed directly: with no template shape hint at all, a real
    # generated design document had zero sequence_flows/class_design
    # anywhere, so no low-level UML diagram ever had a chance to render,
    # even though this renderer fully supports it given the right shape.
    data = {
        "document_metadata": {
            "document_id": "DOC-1", "document_type": "LLD", "system_name": "Checkout",
            "title": "Checkout Design", "version": "1.0", "status": "draft",
        },
        "low_level_design": {
            "components": [{
                "component_name": "Checkout Service",
                "description": "Handles checkout.",
                "responsibilities": ["Validate cart"],
                "sequence_flows": [{
                    "diagram_id": "SEQ-1", "diagram_type": "sequence", "notation_standard": "UML",
                    "title": "Checkout Sequence", "description": "Checkout flow.",
                    "participants": ["Client", "Checkout Service", "Payment Gateway"],
                    "steps": [
                        {"step_number": 1, "from_participant": "Client", "to_participant": "Checkout Service",
                         "message": "submitOrder()"},
                        {"step_number": 2, "from_participant": "Checkout Service", "to_participant": "Payment Gateway",
                         "message": "charge()"},
                    ],
                }],
            }],
        },
    }
    with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(data, f)

    result = create_standard_doc_from_file("Checkout", schema_type="design")
    assert result.startswith("SUCCESS:")

    doc = docx.Document(os.path.join(paths.OUTPUT_DIR, "Checkout_Design.docx"))
    body_text = "\n".join(p.text for p in doc.paragraphs)

    assert len(doc.inline_shapes) >= 1
    assert "Checkout Sequence" in body_text
    assert "not yet generated" not in body_text
