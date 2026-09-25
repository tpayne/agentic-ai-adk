# process_agents/helpers/doc_design_sections.py
#
# Bespoke, table-driven renderers for design-document sections that
# review feedback asked to be restructured away from the generic
# fallback renderer (_render_generic_value): Requirements, System
# Context, Quality Attributes, Compliance and Standards, and the Risk
# Register. The generic renderer dumps every schema field with no fixed
# column set and no explanatory opening paragraph, which is fine for
# sections with no bespoke renderer yet, but produced tables that mixed
# in fields a reviewer didn't want (source, linked_process_step, status,
# sub_characteristic, ...) and gave no indication of what the section
# covers. Every renderer here:
#   - adds a short opening paragraph saying what the section is about
#     (and another one per subsection, where a section has more than
#     one table)
#   - shows only the columns review feedback asked for, dropping the
#     rest of each record's fields
#   - sorts rows for a stable, predictable reading order
#   - returns True/False so callers can skip page breaks around a
#     silent no-op, the same convention every other section-adding
#     function in this pipeline follows

import re
import traceback
import logging

import docx
from docx.shared import Inches, Pt

from .doc_structure import (
    apply_iso_table_formatting,
    _set_cell_bullets,
    _leading_number,
)
from .doc_content import _render_diagram_descriptor

logger = logging.getLogger("ProcessArchitect.DocDesignSections")


# ============================================================
# Shared sort helpers
# ============================================================

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _priority_sort_key(priority) -> int:
    return _PRIORITY_ORDER.get(str(priority or "").strip().lower(), 99)


def _natural_sort_key(value):
    """
    Splits an id like "FR-002" into ["fr-", 2, ""] so ids sort
    numerically within their prefix ("FR-2" before "FR-10") instead of
    lexicographically (which would otherwise put "FR-10" before "FR-2").
    """
    parts = re.split(r"(\d+)", str(value or ""))
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def _set_header_row(table, headers) -> None:
    for idx, label in enumerate(headers):
        table.rows[0].cells[idx].text = label


# ============================================================
# 3.0 REQUIREMENTS
# ============================================================

def _add_requirements_table(doc: docx.Document, items, include_category: bool) -> None:
    items = [i for i in items if isinstance(i, dict)]
    items = sorted(
        items,
        key=lambda r: (_natural_sort_key(r.get("id")), _priority_sort_key(r.get("priority"))),
    )

    headers = ["ID", "Priority"]
    if include_category:
        headers.append("Category")
    headers += ["Description", "Acceptance Criteria"]

    table = doc.add_table(rows=1, cols=len(headers))
    _set_header_row(table, headers)

    for item in items:
        row = table.add_row().cells
        col = 0
        row[col].text = str(item.get("id", "")); col += 1
        row[col].text = str(item.get("priority", "")).replace("_", " ").title(); col += 1

        if include_category:
            characteristic = str(item.get("characteristic") or "").replace("_", " ").title()
            sub = item.get("sub_characteristic")
            row[col].text = f"{characteristic} ({sub})" if characteristic and sub else (characteristic or str(sub or ""))
            col += 1

        _set_cell_bullets(row[col], item.get("description")); col += 1
        _set_cell_bullets(row[col], item.get("acceptance_criteria"))

    apply_iso_table_formatting(table, doc)
    doc.add_paragraph()


def _add_requirements_section(
    doc: docx.Document, requirements: dict, heading: str = "3.0 Requirements",
) -> bool:
    """
    3.0 Requirements — ISO/IEC/IEEE 29148 style. Functional and
    non-functional requirements each get their own opening paragraph and
    a fixed-column, consistently X.X-numbered table (id / priority /
    description / acceptance criteria, plus a category column derived
    from the ISO/IEC 25010 characteristic for non-functional
    requirements), sorted by id then priority, per review feedback.
    Every other requirement field (source, linked_process_step, status,
    the traceability matrix) is intentionally left out of this table —
    "you can ignore the rest of the requirement details".
    """
    try:
        if not isinstance(requirements, dict) or not requirements:
            return False

        functional = requirements.get("functional_requirements")
        non_functional = requirements.get("non_functional_requirements")

        if not functional and not non_functional:
            return False

        lead = _leading_number(heading, default=3)

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section defines the functional and non-functional requirements "
            "this design must satisfy, following ISO/IEC/IEEE 29148 requirements "
            "engineering practice. Each requirement table below is ordered by "
            "identifier, then by priority."
        )

        subsection = 1

        if isinstance(functional, list) and functional:
            doc.add_heading(f"{lead}.{subsection} Functional Requirements", level=2)
            subsection += 1
            doc.add_paragraph(
                "The following functional requirements describe the capabilities "
                "this design must provide."
            )
            _add_requirements_table(doc, functional, include_category=False)

        if isinstance(non_functional, list) and non_functional:
            doc.add_heading(f"{lead}.{subsection} Non-Functional Requirements", level=2)
            subsection += 1
            doc.add_paragraph(
                "The following non-functional requirements describe the quality "
                "attributes and operating constraints this design must satisfy "
                "(ISO/IEC 25010)."
            )
            _add_requirements_table(doc, non_functional, include_category=True)

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 4.0 SYSTEM CONTEXT
# ============================================================

def _add_system_context_section(
    doc: docx.Document, system_context: dict, heading: str = "4.0 System Context",
    system_name: str = None,
) -> bool:
    """
    4.0 System Context — C4 model "System Context" (Level 1) equivalent.
    Actors and external systems each get an opening paragraph and their
    own table; external systems only show the columns that are actually
    populated anywhere in the list (the schema makes every field but
    "name" optional), rather than a fixed set that could end up mostly
    blank.
    """
    try:
        if not isinstance(system_context, dict) or not system_context:
            return False

        actors = system_context.get("actors")
        external_systems = system_context.get("external_systems")
        context_diagram = system_context.get("context_diagram")

        if not actors and not external_systems and not context_diagram:
            return False

        lead = _leading_number(heading, default=4)
        hub_name = system_name or "this system"

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            f"This section defines the boundary of {hub_name}: the actors and "
            "external systems it interacts with, following the C4 model's "
            "System Context (Level 1) view."
        )

        subsection = 1

        if isinstance(actors, list) and actors:
            doc.add_heading(f"{lead}.{subsection} Actors", level=2)
            subsection += 1
            doc.add_paragraph("The following actors interact with the system:")

            table = doc.add_table(rows=1, cols=3)
            _set_header_row(table, ["Name", "Type", "Description"])
            for a in actors:
                if not isinstance(a, dict):
                    continue
                row = table.add_row().cells
                row[0].text = str(a.get("name", ""))
                row[1].text = str(a.get("type", "")).replace("_", " ").title()
                row[2].text = str(a.get("description", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if isinstance(external_systems, list) and external_systems:
            doc.add_heading(f"{lead}.{subsection} External Systems", level=2)
            subsection += 1
            doc.add_paragraph("The following external systems integrate with this system:")

            candidate_cols = [
                ("name", "Name"),
                ("description", "Description"),
                ("interface_type", "Interface Type"),
                ("data_exchanged", "Data Exchanged"),
                ("owner", "Owner"),
            ]
            present_cols = [
                col for col in candidate_cols
                if any(isinstance(e, dict) and e.get(col[0]) for e in external_systems)
            ] or [candidate_cols[0]]

            table = doc.add_table(rows=1, cols=len(present_cols))
            _set_header_row(table, [label for _, label in present_cols])
            for e in sorted(
                (e for e in external_systems if isinstance(e, dict)),
                key=lambda e: _natural_sort_key(e.get("name")),
            ):
                row = table.add_row().cells
                for idx, (key, _) in enumerate(present_cols):
                    row[idx].text = str(e.get(key, ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if isinstance(context_diagram, dict) and context_diagram:
            _render_diagram_descriptor(
                doc, context_diagram, level=2, context=system_context, system_name=system_name
            )

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 7.0 QUALITY ATTRIBUTES
# ============================================================

def _add_quality_attributes_section(
    doc: docx.Document, quality_attributes, heading: str = "7.0 Quality Attributes",
) -> bool:
    """
    Quality Attributes — ISO/IEC 25010. One table: Category (the
    ISO/IEC 25010 characteristic, plus sub-characteristic where given),
    Description, Measure Method, Metric, Target. Every other field on
    the record is dropped, per review feedback ("you can drop
    irrelevant other columns").
    """
    try:
        items = [q for q in (quality_attributes or []) if isinstance(q, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section defines the quality attributes this design targets, "
            "mapped to ISO/IEC 25010 product quality characteristics."
        )

        items = sorted(
            items,
            key=lambda q: (
                str(q.get("characteristic") or "").lower(),
                str(q.get("sub_characteristic") or "").lower(),
            ),
        )

        headers = ["Category", "Description", "Measure Method", "Metric", "Target"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)

        for q in items:
            row = table.add_row().cells
            characteristic = str(q.get("characteristic") or "").replace("_", " ").title()
            sub = q.get("sub_characteristic")
            row[0].text = f"{characteristic} ({sub})" if characteristic and sub else (characteristic or str(sub or ""))
            _set_cell_bullets(row[1], q.get("description"))
            _set_cell_bullets(row[2], q.get("measurement_method"))
            row[3].text = str(q.get("metric") or "")
            row[4].text = str(q.get("target") or "")

        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 8.0 COMPLIANCE AND STANDARDS
# ============================================================

def _add_compliance_and_standards_section(
    doc: docx.Document, compliance_and_standards: dict, heading: str = "8.0 Compliance and Standards",
) -> bool:
    """
    Compliance and Standards. Two subsections, each with its own table:
    Applicable Standards (Standard, Body, Clause Reference,
    Applicability, Compliance Status) and Regulatory Requirements
    (Regulation, Jurisdiction, Requirement (bulleted), Compliance
    Status). Review feedback asked for "Standards" as a table with an
    opening paragraph but didn't specify columns for it (unlike Quality
    Attributes/Risk Register, whose columns it spelled out) -- these are
    a best-guess default straight from the schema's own field names, so
    flag any columns you'd rather see instead.
    """
    try:
        if not isinstance(compliance_and_standards, dict) or not compliance_and_standards:
            return False

        applicable_standards = compliance_and_standards.get("applicable_standards")
        regulatory_requirements = compliance_and_standards.get("regulatory_requirements")

        if not applicable_standards and not regulatory_requirements:
            return False

        lead = _leading_number(heading, default=8)

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section lists the standards and regulatory requirements "
            "applicable to this design, and its current compliance status "
            "against each."
        )

        subsection = 1

        if isinstance(applicable_standards, list) and applicable_standards:
            doc.add_heading(f"{lead}.{subsection} Applicable Standards", level=2)
            subsection += 1
            doc.add_paragraph("The following standards apply to this design:")

            headers = ["Standard", "Body", "Clause Reference", "Applicability", "Compliance Status"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)

            items = sorted(
                (s for s in applicable_standards if isinstance(s, dict)),
                key=lambda s: str(s.get("standard_name") or "").lower(),
            )
            for s in items:
                row = table.add_row().cells
                row[0].text = str(s.get("standard_name", ""))
                row[1].text = str(s.get("standard_body", ""))
                row[2].text = str(s.get("clause_reference", ""))
                _set_cell_bullets(row[3], s.get("applicability"))
                row[4].text = str(s.get("compliance_status", "")).replace("_", " ").title()
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if isinstance(regulatory_requirements, list) and regulatory_requirements:
            doc.add_heading(f"{lead}.{subsection} Regulatory Requirements", level=2)
            subsection += 1
            doc.add_paragraph("The following regulatory requirements apply to this design:")

            headers = ["Regulation", "Jurisdiction", "Requirement", "Compliance Status"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)

            items = sorted(
                (r for r in regulatory_requirements if isinstance(r, dict)),
                key=lambda r: str(r.get("regulation_name") or "").lower(),
            )
            for r in items:
                row = table.add_row().cells
                row[0].text = str(r.get("regulation_name", ""))
                row[1].text = str(r.get("jurisdiction", ""))
                _set_cell_bullets(row[2], r.get("requirement_description"))
                row[3].text = str(r.get("compliance_status", "")).replace("_", " ").title()
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 9.0 RISK REGISTER
# ============================================================

def _add_risk_register_section(
    doc: docx.Document, risk_register, heading: str = "9.0 Risk Register",
) -> bool:
    """
    Risk Register. One table: ID, Category, Likelihood, Impact,
    Description (bulleted), Mitigation (bulleted) -- "owner" and
    "status" are dropped as the least essential fields, the same way
    Quality Attributes/Requirements dropped their own least-essential
    fields, since review feedback didn't spell out this table's columns
    the way it did for those two. Ordered by id.
    """
    try:
        items = [r for r in (risk_register or []) if isinstance(r, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section documents the risks identified for this design, their "
            "likelihood and impact, and the mitigations in place."
        )

        items = sorted(items, key=lambda r: _natural_sort_key(r.get("id")))

        headers = ["ID", "Category", "Likelihood", "Impact", "Description", "Mitigation"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)

        for r in items:
            row = table.add_row().cells
            row[0].text = str(r.get("id", ""))
            row[1].text = str(r.get("category", ""))
            row[2].text = str(r.get("likelihood", "")).title()
            row[3].text = str(r.get("impact", "")).title()
            _set_cell_bullets(row[4], r.get("description"))
            _set_cell_bullets(row[5], r.get("mitigation"))

        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 5.0 ARCHITECTURE DESCRIPTION -- ARCHITECTURE ANALYSIS
# ============================================================

def _bullet_at(doc: docx.Document, text: str, indent_inches: float) -> None:
    """Like doc_structure._add_bullet, but with an arbitrary indent depth
    instead of a fixed on/off 0.3in, so alternative-level bullets can sit
    one level deeper than the top-level Strengths/Weaknesses/Risks ones."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.left_indent = Inches(indent_inches)
    p.add_run(f"• {text}")


def _add_bulleted_group(doc: docx.Document, label: str, values, indent_inches: float) -> None:
    """A bold 'Label:' line followed by one bullet per item, all at
    `indent_inches`. No-op if `values` is empty, so an item with no
    weaknesses (say) doesn't print an empty "Weaknesses:" header."""
    values = [v for v in (values or []) if isinstance(v, str) and v.strip()]
    if not values:
        return
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(indent_inches)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(0)
    p.add_run(f"{label}:").bold = True
    for v in values:
        _bullet_at(doc, v, indent_inches)


def _add_architecture_analysis(doc: docx.Document, architecture_analysis, level: int = 3) -> bool:
    """
    Architecture Analysis -- description/strengths/weaknesses/risks of
    an architectural approach, any alternatives considered on the same
    basis, and a recommendation (see design_document_schema.json's
    $defs.architectureAnalysis). Deliberately replaces the earlier
    ADR-style rendering (id/title/status/context/decision/consequences/
    alternatives_considered/date/decided_by), per review feedback that
    it contained "a lot of hallucinated detail about decisions that
    were never made": framing the generating agent's own analysis as a
    minuted decision, made by a named person on a specific date, gave
    it a fact it doesn't have and was fabricating one instead. Nothing
    rendered here is a status, a date, or a "decided by" -- the schema
    no longer carries those fields at all, so there's nothing left to
    fabricate.

    One heading per architecture_analysis entry (its own "title"), each
    followed by: a description paragraph; Strengths/Weaknesses/Risks as
    bold-labelled bullet lists; an "Alternatives Considered" block (only
    if the entry has any) with the same Strengths/Weaknesses/Risks shape
    per alternative plus what it resolves or introduces compared to the
    description above; and a closing Recommendation paragraph.
    """
    try:
        items = [a for a in (architecture_analysis or []) if isinstance(a, dict)]
        if not items:
            return False

        heading_level = min(max(level, 1), 6)

        for item in items:
            title = item.get("title") or "Architecture"
            doc.add_heading(str(title), level=heading_level)

            description = item.get("description")
            if description:
                doc.add_paragraph(str(description))

            for field, label in (
                ("strengths", "Strengths"), ("weaknesses", "Weaknesses"), ("risks", "Risks"),
            ):
                _add_bulleted_group(doc, label, item.get(field), indent_inches=0.0)

            alternatives = [a for a in (item.get("alternatives") or []) if isinstance(a, dict)]
            if alternatives:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(10)
                p.add_run("Alternatives Considered").bold = True

                for alt in alternatives:
                    option = alt.get("option") or "Alternative"
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Inches(0.3)
                    p.paragraph_format.space_before = Pt(8)
                    p.add_run(str(option)).bold = True

                    alt_description = alt.get("description")
                    if alt_description:
                        p = doc.add_paragraph(str(alt_description))
                        p.paragraph_format.left_indent = Inches(0.3)

                    for field, label in (("strengths", "Strengths"), ("weaknesses", "Weaknesses")):
                        _add_bulleted_group(doc, label, alt.get(field), indent_inches=0.3)

                    comparison = alt.get("comparison_to_recommended")
                    if comparison:
                        _add_bulleted_group(
                            doc, "Compared to the Above", [str(comparison)], indent_inches=0.3
                        )

                    _add_bulleted_group(doc, "Risks", alt.get("risks"), indent_inches=0.3)

            recommendation = item.get("recommendation")
            if recommendation:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(10)
                p.add_run("Recommendation: ").bold = True
                p.add_run(str(recommendation))

            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False
