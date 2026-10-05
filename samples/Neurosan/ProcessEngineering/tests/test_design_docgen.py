"""Exercises the design-document generation stage end-to-end against the
real CodedTool classes, mirroring tests/test_docgen.py's process-schema
coverage. The isolated_output_dir autouse fixture (conftest.py) means every
assertion here reads/writes only a throwaway tmp_path.
"""

import json
import os

import docx

from coded_tools.common import paths
from coded_tools.common.process_json import DESIGN_JSON_FILENAME
from coded_tools.common.docgen.edge_inference import generate_clean_diagram
from coded_tools.common.docgen.generation import create_standard_doc_from_file
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


def _write_sample_design_json():
    with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(SAMPLE_DESIGN, f)


def test_generate_clean_diagram_produces_a_png_for_a_design_document():
    _write_sample_design_json()

    result = generate_clean_diagram()

    assert "Diagram successfully generated at" in result
    assert os.path.exists(os.path.join(paths.OUTPUT_DIR, "checkout_combined_design_flow.png"))


def test_create_standard_doc_from_file_builds_a_real_design_docx_with_expected_sections():
    _write_sample_design_json()

    result = create_standard_doc_from_file("Checkout", schema_type="design")

    assert result.startswith("SUCCESS:")
    out_path = os.path.join(paths.OUTPUT_DIR, "Checkout_Combined_Design.docx")
    assert os.path.exists(out_path)

    doc = docx.Document(out_path)
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
