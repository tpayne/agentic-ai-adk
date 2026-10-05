"""Exercises the process document-generation stage end-to-end against the
real CodedTool classes: flow-diagram inference (edge_inference.py) and the
ISO-formatted Word document builder (generation.py). The isolated_output_dir
autouse fixture (conftest.py) means every assertion here reads/writes only
a throwaway tmp_path, never the real project's output/.
"""

import json
import os

import docx
import pytest

from coded_tools.common import paths
from coded_tools.common.process_json import PROCESS_JSON_FILENAME
from coded_tools.common.docgen.edge_inference import generate_clean_diagram
from coded_tools.common.docgen.generation import create_standard_doc_from_file
from coded_tools.process.edge_inference_tool import GenerateProcessFlowDiagramCodedTool
from coded_tools.process.doc_generation_tool import GenerateProcessDocumentCodedTool

SAMPLE_PROCESS = {
    "process_name": "Vendor Onboarding",
    "version": "1.0",
    "industry_sector": "Procurement",
    "introduction": "Onboards new vendors with KYC checks.",
    "assumptions": ["Vendor has a valid tax ID."],
    "constraints": ["Must complete within 5 business days."],
    "stakeholders": [{"stakeholder_name": "Procurement Lead", "responsibilities": ["Approve vendor"]}],
    "process_steps": [
        {
            "step_name": "Collect Vendor Documents", "description": "Gather required docs.",
            "responsible_party": "Procurement Lead", "dependencies": [],
        },
        {
            "step_name": "KYC Check", "description": "Run KYC verification.",
            "responsible_party": "Compliance Officer", "dependencies": ["Collect Vendor Documents"],
        },
    ],
    "tools_summary": [{"category": "KYC", "tools": ["Thomson Reuters"]}],
    "metrics": ["Cycle time under 5 days"],
    "governance_requirements": ["Quarterly audit"],
    "risks_and_controls": [{"risk": "Fraud", "control": "KYC check"}],
    "process_triggers": ["New vendor request submitted"],
    "process_end_conditions": ["Vendor approved and onboarded"],
    "change_management": [{"change_request_process": "Submit via ticket", "versioning_rules": "Semantic versioning"}],
    "continuous_improvement": [{"review_frequency": "Quarterly", "improvement_inputs": ["Audit findings"]}],
    "appendix": {"reference_docs": {"summary": "KYC policy doc"}},
}


def _write_sample_process_json():
    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(SAMPLE_PROCESS, f)


def test_generate_clean_diagram_produces_a_png_named_after_the_process():
    _write_sample_process_json()

    result = generate_clean_diagram()

    assert "Diagram successfully generated at" in result
    assert os.path.exists(os.path.join(paths.OUTPUT_DIR, "vendor_onboarding_flow.png"))


def test_generate_clean_diagram_falls_back_when_no_process_json_exists():
    # No process_data.json written -- must not raise, must still produce a
    # Start->End fallback diagram rather than erroring out.
    result = generate_clean_diagram()
    assert "Diagram successfully generated at" in result


def test_create_standard_doc_from_file_builds_a_real_docx_with_expected_sections():
    _write_sample_process_json()

    result = create_standard_doc_from_file("Vendor Onboarding", schema_type="process")

    assert result.startswith("SUCCESS:")
    out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Onboarding.docx")
    assert os.path.exists(out_path)

    doc = docx.Document(out_path)
    heading_texts = [
        p.text for p in doc.paragraphs
        if p.style is not None and p.style.name == "Heading 1"
    ]
    assert "1.0 Process Overview" in heading_texts
    assert "2.0 Stakeholders and Responsibilities" in heading_texts
    assert "3.0 Process Workflow" in heading_texts
    assert "12.0 Governance Requirements" in heading_texts
    assert "13.0 Risks and Controls" in heading_texts
    assert any(h.startswith("Appendix A") for h in heading_texts)
    assert any(h.startswith("Appendix C: Glossary") for h in heading_texts)


def test_generate_process_flow_diagram_coded_tool_invoke():
    _write_sample_process_json()
    tool = GenerateProcessFlowDiagramCodedTool()
    result = tool.invoke({}, {})
    assert "Diagram successfully generated at" in result


def test_generate_process_document_coded_tool_invoke_uses_fallback_name_when_missing():
    # The process JSON's own "process_name" wins even if the tool's
    # fallback argument differs or is omitted entirely.
    _write_sample_process_json()
    tool = GenerateProcessDocumentCodedTool()
    result = tool.invoke({}, {})
    assert result.startswith("SUCCESS:")
    assert os.path.exists(os.path.join(paths.OUTPUT_DIR, "Vendor_Onboarding.docx"))
