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
from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME
from process_toolkit.docgen.edge_inference import generate_clean_diagram
from process_toolkit.docgen.generation import create_standard_doc_from_file
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

    # Document generation itself must create/embed the image; the pipeline's
    # separate diagram-tool call is not a prerequisite.
    result = create_standard_doc_from_file("Vendor Onboarding", schema_type="process")

    assert result.startswith("SUCCESS:")
    out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Onboarding.docx")
    assert os.path.exists(out_path)

    doc = docx.Document(out_path)
    assert len(doc.inline_shapes) == 1
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


def test_process_document_generates_and_embeds_subprocess_diagrams():
    _write_sample_process_json()
    subprocess_dir = os.path.join(paths.OUTPUT_DIR, "subprocesses")
    os.makedirs(subprocess_dir, exist_ok=True)
    with open(os.path.join(subprocess_dir, "KYC_Check.json"), "w", encoding="utf-8") as f:
        json.dump({
            "step_name": "KYC Check",
            "subprocess_flow": [
                {"substep_name": "Collect Documents", "responsible_party": "Vendor"},
                {"substep_name": "Verify Identity", "responsible_party": "Compliance"},
                {"substep_name": "Record Outcome", "responsible_party": "Compliance"},
            ],
        }, f)

    result = create_standard_doc_from_file("Vendor Onboarding", schema_type="process")

    assert result.startswith("SUCCESS:")
    out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Onboarding.docx")
    doc = docx.Document(out_path)
    assert len(doc.inline_shapes) == 2
    assert os.path.isfile(os.path.join(paths.OUTPUT_DIR, "vendor_onboarding_flow.png"))
    assert os.path.isfile(os.path.join(paths.OUTPUT_DIR, "step_diagrams", "KYC_Check.png"))


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


# ============================================================
# Real-world field shape regressions.
#
# A live LLM run surfaced several fields shaped differently than
# SAMPLE_PROCESS above: id-tagged traceability dicts
# ({"id": "CON-001", "description": "..."}) instead of plain strings for
# constraints/metrics/CSF/CFF/reporting_and_analytics/governance_
# requirements/process_triggers/process_end_conditions, plain descriptive
# STRINGS (not lists of objects) for change_management/
# continuous_improvement, and stakeholders with "role" as a descriptive
# sentence but no separate "responsibilities" list. Each of these silently
# dropped or blanked real content before the fixes in content.py/
# governance.py/technical.py/structure.py/process_json.py. These tests
# pin that real-world shape down directly so it can't regress.
# ============================================================

REAL_WORLD_PROCESS = {
    "process_name": "GitOps Scrum Process",
    "version": "1.0",
    "industry_sector": "Software Engineering",
    "introduction": "Manages feature delivery using Scrum and GitOps.",
    "purpose": "Deliver features predictably using GitOps-driven deployments.",
    "scope": "Covers planning through production deployment.",
    "process_owner": "Engineering Director",
    "assumptions": [{"id": "ASM-001", "assumption": "Team has CI/CD access."}],
    "constraints": [{"id": "CON-001", "description": "Must comply with change-control policy."}],
    "stakeholders": [
        {"role": "Primary individual developer of features and bug fixes.", "name": "Developer"},
        {"name": "Product Owner", "role": "Defines requirements and priorities; verifies features."},
    ],
    "process_steps": [
        {
            "step_name": "Plan Sprint", "description": "Plan sprint backlog.",
            "responsible_party": "Scrum Master", "dependencies": [],
        },
    ],
    "metrics": [{"id": "MET-001", "metric": "Sprint Velocity", "description": "Story points completed per sprint."}],
    "critical_success_factors": [{"id": "CSF-001", "factor": "Fast feedback loops"}],
    "critical_failure_factors": [{"id": "CFF-001", "factor": "Unreviewed production changes"}],
    "reporting_and_analytics": [{"id": "REP-001", "metric": "Sprint Burndown", "description": "Tracks remaining work."}],
    "governance_requirements": [{"id": "GOV-001", "requirement": "All changes require peer review."}],
    "process_triggers": [{"id": "TRG-001", "trigger": "New sprint begins."}],
    "process_end_conditions": [{"id": "END-001", "condition": "All sprint goals met or carried over."}],
    "change_management": "All changes go through pull request review and semantic versioning.",
    "continuous_improvement": "Retrospectives run at the end of every sprint to drive process improvements.",
    "risks_and_controls": [{"risk": "Merge conflicts", "control": "Frequent rebasing"}],
}


def _write_real_world_process_json():
    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(REAL_WORLD_PROCESS, f)


def _all_table_rows(doc):
    """Returns every table row (as a list of cell text), across every
    table in the document, so assertions can match on cell content
    without needing to track which section a table belongs to."""
    return [[c.text for c in row.cells] for table in doc.tables for row in table.rows]


def test_real_world_doc_renders_id_tagged_dicts_and_string_shapes():
    _write_real_world_process_json()

    result = create_standard_doc_from_file("GitOps Scrum Process", schema_type="process")
    assert result.startswith("SUCCESS:")

    out_path = os.path.join(paths.OUTPUT_DIR, "GitOps_Scrum_Process.docx")
    doc = docx.Document(out_path)

    body_text = "\n".join(p.text for p in doc.paragraphs)
    all_rows = _all_table_rows(doc)
    flat_cells = [cell for row in all_rows for cell in row]

    # id-tagged constraint/assumption bullets render the real description,
    # not "iddescription"-style garbage from iterating a dict as a string.
    assert "Must comply with change-control policy." in body_text
    assert "Team has CI/CD access." in body_text

    # process_owner (not just the ADK's own "owner" key) renders.
    assert "Engineering Director" in body_text
    # purpose/scope render in Overview and are not duplicated into Appendix B.
    assert "Deliver features predictably using GitOps-driven deployments." in body_text
    assert "Covers planning through production deployment." in body_text

    # id-tagged metrics/CSF/CFF/reporting_and_analytics show their real
    # name instead of a blank placeholder cell.
    assert "Sprint Velocity" in flat_cells
    assert "Fast feedback loops" in flat_cells
    assert "Unreviewed production changes" in flat_cells
    assert "Sprint Burndown" in flat_cells

    # id-tagged governance/triggers/end-conditions bullets render their
    # real text.
    assert "All changes require peer review." in body_text
    assert "New sprint begins." in body_text
    assert "All sprint goals met or carried over." in body_text

    # change_management/continuous_improvement given as plain strings
    # render as a paragraph instead of being silently dropped.
    assert "pull request review and semantic versioning" in body_text
    assert "Retrospectives run at the end of every sprint" in body_text

    # Stakeholders: "role" wins as Responsibilities whenever a distinct
    # "name" was used for the Stakeholder column.
    assert "Developer" in flat_cells
    assert "Primary individual developer of features and bug fixes." in flat_cells
    assert "Defines requirements and priorities; verifies features." in flat_cells


# ============================================================
# Matplotlib warning regression (edge_inference.py).
#
# This doesn't raise -- it's a logged UserWarning on an otherwise
# successful run -- but it's a real, root-cause-fixable issue (a
# tight_layout() call that can't reconcile with far-left swimlane-label
# text), not noise to silence. simplefilter("error") turns the warning
# into a failure so a regression is caught the same way a raised
# exception would be. The equivalent step_diagrams.py regression test now
# lives in shared/process_toolkit/tests/docgen/test_step_diagrams.py.
# ============================================================

def test_flow_diagram_non_start_end_node_label_does_not_warn():
    import warnings

    _write_sample_process_json()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = generate_clean_diagram()
    assert "Diagram successfully generated at" in result
