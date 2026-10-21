"""End-to-end coverage for generation.py's own page-break bookkeeping --
NOT per-section content (see test_content.py/test_design_sections.py for
that), just "does the final document ever place two page breaks back to
back with nothing real between them," which Word renders as a fully
blank page.
"""

import json

import docx
from docx.oxml.ns import qn

from process_toolkit import paths
from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME
from process_toolkit.docgen.generation import create_standard_doc_from_file


def _has_page_break(p_elem) -> bool:
    return any(br.get(qn("w:type")) == "page" for br in p_elem.findall(".//" + qn("w:br")))


def _has_image(p_elem) -> bool:
    return len(p_elem.findall(".//" + qn("w:drawing"))) > 0


def _has_text(p_elem) -> bool:
    return any((t.text or "").strip() for t in p_elem.findall(".//" + qn("w:t")))


def _blank_page_gaps(docx_path: str) -> list:
    """
    Returns a list of (break_index_a, break_index_b) pairs for every
    place two page breaks appear with NO real content (text, image, or
    table) between them -- i.e. every FULLY BLANK page Word would
    actually render. Walks doc.element.body directly (not
    doc.paragraphs/doc.tables separately), since those two don't
    preserve true document order relative to each other -- a table
    sitting between two breaks would be invisible to a paragraphs-only
    check and wrongly reported as a blank page.
    """
    doc = docx.Document(docx_path)
    items = []
    for child in doc.element.body:
        if child.tag == qn("w:p"):
            items.append(("p", child))
        elif child.tag == qn("w:tbl"):
            items.append(("tbl", child))

    break_idxs = [i for i, (t, el) in enumerate(items) if t == "p" and _has_page_break(el)]
    gaps = []
    for bi in range(len(break_idxs) - 1):
        segment = items[break_idxs[bi] + 1:break_idxs[bi + 1]]
        has_real_content = any(
            kind == "tbl" or (kind == "p" and (_has_text(el) or _has_image(el)))
            for kind, el in segment
        )
        if not has_real_content:
            gaps.append((break_idxs[bi], break_idxs[bi + 1]))
    return gaps


# Deliberately has NO "appendix" key, and every other top-level key is one
# generation.py's own consumed_keys set already accounts for -- so BOTH
# _add_appendix_from_json (gated on "if appendix:") and
# _add_additional_data_section (nothing left over once every field is
# consumed) have nothing to render. This is the exact combination that
# triggered the bug: two unconditional add_iso_page_break(doc) calls
# fired back-to-back around these two no-op sections, rendering as a
# fully blank page right before "Appendix B" in a real generated
# document, confirmed directly.
SAMPLE_PROCESS_NO_APPENDIX_NO_EXTRA_DATA = {
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
    ],
    "governance_requirements": ["Quarterly audit"],
    "risks_and_controls": [{"risk": "Fraud", "control": "KYC check"}],
    "process_triggers": ["New vendor request submitted"],
    "process_end_conditions": ["Vendor approved and onboarded"],
    "change_management": [{"change_request_process": "Submit via ticket", "versioning_rules": "Semantic versioning"}],
    "continuous_improvement": [{"review_frequency": "Quarterly", "improvement_inputs": ["Audit findings"]}],
}


def test_no_blank_page_when_appendix_and_additional_data_are_both_absent():
    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(SAMPLE_PROCESS_NO_APPENDIX_NO_EXTRA_DATA, f)

    result = create_standard_doc_from_file("Vendor Onboarding", schema_type="process")
    assert result.startswith("SUCCESS:")

    out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
    gaps = _blank_page_gaps(out_path)
    assert gaps == [], f"found {len(gaps)} fully blank page(s) at break-index pairs {gaps}"
