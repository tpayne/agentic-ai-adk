"""Bespoke renderers for the proposal-response document: Executive
Summary, Our Understanding of Your Requirements, Proposed Solution,
Solution Architecture (embeds a generated component diagram), Deliverables,
Differentiators, the Compliance Matrix (the central traceability table,
one row per requirement id from the SOURCE requirements_summary.json
that Proposal_Response_Agent drafted this response against, each with an
Evidence/Location pointer into this same document), the Implementation
Plan (a phased delivery timeline), Qualifications, Assumptions, Risks and
Mitigations, Pricing Approach (prose plus an itemized pricing table),
Open Questions for Clarification, and Unaddressed Items -- rendered
directly from proposal_response.json's own fields (see
process_toolkit.proposal_response.proposal_response and
process_toolkit.schema.proposal_response_json for that shape).

Follows requirements_sections.py's own conventions exactly: a short
opening paragraph, a fixed set of columns, natural-id sort,
apply_iso_table_formatting/_set_cell_bullets, True/False no-op-render
return.
"""

import traceback

import docx
from docx.shared import Inches

from process_toolkit.docgen.structure import apply_iso_table_formatting, _set_cell_bullets
from process_toolkit.docgen.design_sections import _natural_sort_key
from process_toolkit.docgen.proposal_architecture_diagram import generate_proposal_architecture_diagram


def _set_header_row(table, headers) -> None:
    for idx, label in enumerate(headers):
        table.rows[0].cells[idx].text = label


# ============================================================
# 1.0 EXECUTIVE SUMMARY
# ============================================================

def _add_executive_summary_section(
    doc: docx.Document, data: dict, heading: str = "1.0 Executive Summary",
) -> bool:
    """1.0 Executive Summary -- always renders, same as requirements_
    sections.py's own Introduction and Purpose section: this is the
    document's own opening section, and there is always at least a
    generic narrative to show."""
    try:
        doc.add_heading(heading, level=1)
        summary = data.get("summary")
        doc.add_paragraph(
            str(summary) if summary else
            "This document sets out our response to the requirements identified for this "
            "proposal, including our understanding of those requirements, our proposed "
            "solution, and a point-by-point compliance matrix."
        )
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 2.0 OUR UNDERSTANDING OF YOUR REQUIREMENTS
# ============================================================

def _add_understanding_section(
    doc: docx.Document, data: dict, heading: str = "2.0 Our Understanding of Your Requirements",
) -> bool:
    try:
        understanding = data.get("our_understanding")
        if not understanding:
            return False
        doc.add_heading(heading, level=1)
        doc.add_paragraph(str(understanding))
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 3.0 PROPOSED SOLUTION
# ============================================================

def _add_proposed_solution_section(
    doc: docx.Document, data: dict, heading: str = "3.0 Proposed Solution",
) -> bool:
    try:
        solution = data.get("proposed_solution")
        if not solution:
            return False
        doc.add_heading(heading, level=1)
        doc.add_paragraph(str(solution))
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 4.0 SOLUTION ARCHITECTURE
# ============================================================

def _add_solution_architecture_section(
    doc: docx.Document, components, process_name: str, heading: str = "4.0 Solution Architecture",
) -> bool:
    """4.0 Solution Architecture -- renders a generated component diagram
    (see proposal_architecture_diagram.py) plus a Component/Description
    table underneath for accessibility/non-image contexts. No-op (no
    fabricated section) when "architecture_components" has no usable
    entries -- same convention as every other renderer here."""
    try:
        items = [c for c in (components or []) if isinstance(c, dict) and c.get("name")]
        if not items:
            return False

        diagram_path = generate_proposal_architecture_diagram(items, process_name)

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "The following diagram provides a high-level visualization of the proposed solution's "
            "architecture."
        )
        doc.add_picture(diagram_path, width=Inches(6))
        doc.add_paragraph()

        headers = ["Component", "Description"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for item in items:
            row = table.add_row().cells
            row[0].text = str(item.get("name") or "")
            _set_cell_bullets(row[1], item.get("description"))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 4.0 DELIVERABLES
# ============================================================

def _add_deliverables_section(
    doc: docx.Document, deliverables, heading: str = "4.0 Deliverables",
) -> bool:
    try:
        values = [str(v) for v in (deliverables or []) if isinstance(v, str) and v.strip()]
        if not values:
            return False
        doc.add_heading(heading, level=1)
        for v in values:
            doc.add_paragraph(v, style="List Bullet")
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 4.0 DIFFERENTIATORS
# (section-marker comments below are cosmetic only -- every actual
# heading number gets recomputed from final render order by
# generation.py's own _renumber_design_document_headings)
# ============================================================

def _add_differentiators_section(
    doc: docx.Document, differentiators, heading: str = "4.0 Differentiators",
) -> bool:
    try:
        values = [str(v) for v in (differentiators or []) if isinstance(v, str) and v.strip()]
        if not values:
            return False
        doc.add_heading(heading, level=1)
        for v in values:
            doc.add_paragraph(v, style="List Bullet")
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 5.0 COMPLIANCE MATRIX
# ============================================================

def _add_compliance_matrix_section(
    doc: docx.Document, matrix, heading: str = "5.0 Compliance Matrix",
) -> bool:
    """5.0 Compliance Matrix -- the central artifact of this document: one
    row per requirement id carried over from the SOURCE
    requirements_summary.json's own requirements_register, sorted by
    that same id, so a reader can trace every requirement to a response."""
    try:
        items = [m for m in (matrix or []) if isinstance(m, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section addresses each identified requirement in turn, stating our "
            "compliance status and response."
        )

        items = sorted(items, key=lambda m: _natural_sort_key(m.get("requirement_id")))

        headers = ["ID", "Requirement", "Status", "Response", "Evidence / Location"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for m in items:
            row = table.add_row().cells
            row[0].text = str(m.get("requirement_id") or "")
            _set_cell_bullets(row[1], m.get("requirement_text"))
            row[2].text = str(m.get("response_status") or "")
            _set_cell_bullets(row[3], m.get("response"))
            _set_cell_bullets(row[4], m.get("evidence_ref"))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 6.0 IMPLEMENTATION PLAN
# ============================================================

def _add_implementation_plan_section(
    doc: docx.Document, plan, heading: str = "6.0 Implementation Plan",
) -> bool:
    """6.0 Implementation Plan -- a phased delivery timeline. Rows are left
    in the agent's own given order (not sorted) since phases are
    inherently sequential, unlike the compliance matrix's requirement
    ids."""
    try:
        items = [p for p in (plan or []) if isinstance(p, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        headers = ["Phase", "Timing", "Deliverable", "Acceptance Criteria"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for p in items:
            row = table.add_row().cells
            row[0].text = str(p.get("phase") or "")
            row[1].text = str(p.get("timing") or "")
            _set_cell_bullets(row[2], p.get("deliverable"))
            _set_cell_bullets(row[3], p.get("acceptance_criteria"))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 7.0 QUALIFICATIONS
# ============================================================

def _add_qualifications_section(
    doc: docx.Document, data: dict, heading: str = "6.0 Qualifications",
) -> bool:
    try:
        qualifications = data.get("qualifications")
        if not qualifications:
            return False
        doc.add_heading(heading, level=1)
        doc.add_paragraph(str(qualifications))
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 7.0 ASSUMPTIONS
# ============================================================

def _add_assumptions_section(
    doc: docx.Document, assumptions, heading: str = "7.0 Assumptions",
) -> bool:
    try:
        values = [str(v) for v in (assumptions or []) if isinstance(v, str) and v.strip()]
        if not values:
            return False
        doc.add_heading(heading, level=1)
        for v in values:
            doc.add_paragraph(v, style="List Bullet")
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 8.0 RISKS AND MITIGATIONS
# ============================================================

def _add_risks_and_mitigations_section(
    doc: docx.Document, risks, heading: str = "8.0 Risks and Mitigations",
) -> bool:
    try:
        items = [r for r in (risks or []) if isinstance(r, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        headers = ["Risk", "Mitigation"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for r in items:
            row = table.add_row().cells
            _set_cell_bullets(row[0], r.get("risk"))
            _set_cell_bullets(row[1], r.get("mitigation"))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 9.0 PRICING APPROACH
# ============================================================

def _add_pricing_approach_section(
    doc: docx.Document, data: dict, heading: str = "9.0 Pricing Approach",
) -> bool:
    """9.0 Pricing Approach -- the pricing-model prose plus, when present,
    an itemized pricing_table breakdown underneath. Renders if EITHER is
    present; a line item with no actual "price" the user ever gave
    renders as "TBD" rather than being fabricated or dropped."""
    try:
        pricing = data.get("pricing_approach")
        table_items = [p for p in (data.get("pricing_table") or []) if isinstance(p, dict)]
        if not pricing and not table_items:
            return False

        doc.add_heading(heading, level=1)
        if pricing:
            doc.add_paragraph(str(pricing))

        if table_items:
            headers = ["Item", "Basis", "Price"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for item in table_items:
                row = table.add_row().cells
                row[0].text = str(item.get("item") or "")
                _set_cell_bullets(row[1], item.get("basis"))
                row[2].text = str(item.get("price") or "TBD")
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 10.0 OPEN QUESTIONS FOR CLARIFICATION
# ============================================================

def _add_open_questions_section(
    doc: docx.Document, questions, heading: str = "10.0 Open Questions for Clarification",
) -> bool:
    try:
        values = [str(v) for v in (questions or []) if isinstance(v, str) and v.strip()]
        if not values:
            return False
        doc.add_heading(heading, level=1)
        for v in values:
            doc.add_paragraph(v, style="List Bullet")
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 11.0 UNADDRESSED ITEMS
# ============================================================

def _add_unaddressed_items_section(
    doc: docx.Document, items, heading: str = "11.0 Unaddressed Items",
) -> bool:
    """11.0 Unaddressed Items -- carried forward from the SOURCE
    requirements_summary.json's own inferred_requirements/coverage_gaps,
    explicitly flagged here rather than silently dropped."""
    try:
        values = [str(v) for v in (items or []) if isinstance(v, str) and v.strip()]
        if not values:
            return False
        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "The following items were flagged in the original requirements analysis as "
            "inferred or as coverage gaps, not as stated requirements -- they are noted here "
            "for completeness but are not addressed as formal compliance items above."
        )
        for v in values:
            doc.add_paragraph(v, style="List Bullet")
        return True
    except Exception:
        traceback.print_exc()
        return False
