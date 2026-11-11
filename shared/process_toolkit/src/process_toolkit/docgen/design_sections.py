"""Bespoke, table-driven renderers for design-document sections: Requirements,
System Context, Quality Attributes, Compliance and Standards, Risk Register,
Architecture Analysis, Low-Level Design, and Glossary and References. Ported
near-verbatim from the ADK sample's
process_agents/common/helpers/doc_design_sections.py.

Every renderer here adds a short opening paragraph, shows only a fixed set
of columns (dropping the rest of each record's other schema fields), sorts
rows for a stable reading order, and returns True/False so callers can skip
page breaks around a silent no-op -- the same convention every other
section-adding function in this pipeline follows.
"""

import os
import re
import traceback

import docx
from docx.shared import Inches, Pt

from process_toolkit.docgen.structure import (
    apply_iso_table_formatting,
    _set_cell_bullets,
    _leading_number,
)
from process_toolkit.docgen.content import (
    _render_diagram_descriptor,
    _render_generic_value,
    _stringify_nested,
    _add_prose_field,
)
from process_toolkit.docgen.uml_diagrams import generate_uml_diagram

# ============================================================
# Shared sort helpers
# ============================================================

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _priority_sort_key(priority) -> int:
    return _PRIORITY_ORDER.get(str(priority or "").strip().lower(), 99)


def _natural_sort_key(value):
    """Splits an id like "FR-002" into ["fr-", 2, ""] so ids sort
    numerically within their prefix ("FR-2" before "FR-10")."""
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
        # "or" (not a positional .get default) so a present-but-empty
        # string also falls through to "N/A" -- design_document_schema.json
        # marks "id" required for both functional and non-functional
        # requirements, but validate_design_json didn't enforce that
        # (confirmed directly against a real generated design document
        # whose non_functional_requirements were missing it entirely) --
        # that gap is now closed there too, but this still needs its own
        # fallback for documents persisted before that fix existed.
        row[col].text = str(item.get("id") or "N/A"); col += 1
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


def _add_requirements_traceability_table(
    doc: docx.Document, requirements: dict, high_level_design: dict, low_level_design: dict,
) -> bool:
    """Requirements Traceability -- joins every functional/non-functional
    requirement (by id) against (a) the "satisfies_requirements" list on
    every high_level_design/low_level_design component, reversed into
    requirement_id -> [component names], and (b)
    requirements.traceability_matrix[]'s own verification_method for that
    same id. Three columns: Requirement, Satisfying Component(s),
    Verification Method -- a column with no source data shows "—" rather
    than the row being omitted, so a reviewer sees an unsatisfied or
    unverified requirement directly instead of it silently disappearing.
    No-ops (returns False) if neither a component's satisfies_requirements
    nor the traceability_matrix has anything to show -- a bare requirements
    table with every cell reading "—" would add noise, not traceability."""
    functional = [r for r in (requirements.get("functional_requirements") or []) if isinstance(r, dict)]
    non_functional = [r for r in (requirements.get("non_functional_requirements") or []) if isinstance(r, dict)]
    all_reqs = functional + non_functional
    if not all_reqs:
        return False

    satisfying = {}
    for comp_list in (
        (high_level_design or {}).get("components"),
        (low_level_design or {}).get("components"),
    ):
        for comp in (comp_list or []):
            if not isinstance(comp, dict):
                continue
            name = _component_name(comp)
            for rid in (comp.get("satisfies_requirements") or []):
                satisfying.setdefault(str(rid), []).append(name)

    verification = {}
    for entry in (requirements.get("traceability_matrix") or []):
        if isinstance(entry, dict) and entry.get("requirement_id"):
            verification[str(entry["requirement_id"])] = entry.get("verification_method")

    if not satisfying and not verification:
        return False

    doc.add_paragraph(
        "This table traces each requirement to the component(s) that satisfy "
        "it and the method by which it is verified, so a reviewer can confirm "
        "no requirement has been left unaddressed or unverified."
    )

    all_reqs = sorted(all_reqs, key=lambda r: _natural_sort_key(r.get("id")))

    headers = ["Requirement", "Satisfying Component(s)", "Verification Method"]
    table = doc.add_table(rows=1, cols=len(headers))
    _set_header_row(table, headers)

    for r in all_reqs:
        rid = str(r.get("id") or "")
        row = table.add_row().cells
        row[0].text = rid or "N/A"
        comps = satisfying.get(rid)
        row[1].text = ", ".join(dict.fromkeys(comps)) if comps else "—"
        method = verification.get(rid)
        row[2].text = str(method).replace("_", " ").title() if method else "—"

    apply_iso_table_formatting(table, doc)
    doc.add_paragraph()
    return True


def _add_requirements_section(
    doc: docx.Document, requirements: dict, heading: str = "3.0 Requirements",
    high_level_design: dict = None, low_level_design: dict = None,
) -> bool:
    """3.0 Requirements -- ISO/IEC/IEEE 29148 style. Functional and
    non-functional requirements each get their own opening paragraph and
    a fixed-column, X.X-numbered table (id/priority/description/
    acceptance criteria, plus a category column derived from the
    ISO/IEC 25010 characteristic for non-functional requirements), sorted
    by id then priority. If `high_level_design`/`low_level_design` are
    given, a final Requirements Traceability subsection joins requirements
    against each component's own satisfies_requirements and the
    traceability_matrix's verification_method (see
    _add_requirements_traceability_table)."""
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

        if high_level_design is not None or low_level_design is not None:
            heading_pos = doc.add_heading(f"{lead}.{subsection} Requirements Traceability", level=2)
            rendered = _add_requirements_traceability_table(
                doc, requirements, high_level_design or {}, low_level_design or {}
            )
            if not rendered:
                # No satisfies_requirements/traceability_matrix data to show --
                # remove the heading just added rather than leaving an empty
                # "Requirements Traceability" subsection with nothing under it.
                heading_pos._element.getparent().remove(heading_pos._element)

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
    """4.0 System Context -- C4 model "System Context" (Level 1)
    equivalent. Actors and external systems each get an opening paragraph
    and their own table; external systems only show the columns that are
    actually populated anywhere in the list."""
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
                row[2].text = str(a.get("description") or a.get("role") or "")
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
            numbered_diagram = dict(context_diagram)
            diagram_title = numbered_diagram.get("title") or "Context Diagram"
            numbered_diagram["title"] = f"{lead}.{subsection} {diagram_title}"
            _render_diagram_descriptor(
                doc, numbered_diagram, level=2, context=system_context, system_name=system_name
            )
            subsection += 1

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
    """Quality Attributes -- ISO/IEC 25010. One table: Category (the
    characteristic, plus sub-characteristic where given), Description,
    Measure Method, Metric, Target.

    The schema puts one flat metric/target pair directly on each
    characteristic object. A live model instead nested a "metrics" list
    of {metric, target} pairs under each characteristic (reasonable --
    a characteristic plausibly has more than one metric) -- confirmed
    directly against a real generated document, where every row's
    Metric/Target column was blank because the flat keys were never
    present. One table row is now emitted per metric when "metrics" is a
    non-empty list (repeating the characteristic/description/measure
    method), falling back to the flat shape otherwise."""
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
            characteristic = str(q.get("characteristic") or "").replace("_", " ").title()
            sub = q.get("sub_characteristic")
            category_text = (
                f"{characteristic} ({sub})" if characteristic and sub else (characteristic or str(sub or ""))
            )

            metrics = [m for m in (q.get("metrics") or []) if isinstance(m, dict)]
            if metrics:
                for m in metrics:
                    row = table.add_row().cells
                    row[0].text = category_text
                    _set_cell_bullets(row[1], q.get("description"))
                    _set_cell_bullets(row[2], m.get("measurement_method") or q.get("measurement_method"))
                    row[3].text = str(m.get("metric") or "")
                    row[4].text = str(m.get("target") or "")
            else:
                row = table.add_row().cells
                row[0].text = category_text
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
    """Compliance and Standards. Two subsections: Applicable Standards
    (Standard, Body, Clause Reference, Applicability, Compliance Status)
    and Regulatory Requirements (Regulation, Jurisdiction, Requirement,
    Compliance Status).

    "applicable_standards"/"regulatory_requirements" are the schema's own
    top-level keys. A live model instead produced three different,
    non-schema keys here -- "standards_alignment" (standard/description),
    "regulatory_frameworks" (name/description), and
    "compliance_requirements" (id/description) -- confirmed directly
    against a real generated document, where NEITHER expected key was
    present, so this whole section silently rendered nothing at all (not
    even a placeholder) despite real compliance content being present.
    Falling back to these synonyms, with their own differently-named
    fields, recovers that content. Any genuinely unrecognized
    sub-key still safely falls through to Appendix B via
    _build_design_document's consumed_keys."""
    try:
        if not isinstance(compliance_and_standards, dict) or not compliance_and_standards:
            return False

        applicable_standards = (
            compliance_and_standards.get("applicable_standards")
            or compliance_and_standards.get("standards_alignment")
        )
        regulatory_requirements = (
            compliance_and_standards.get("regulatory_requirements")
            or compliance_and_standards.get("regulatory_frameworks")
            or compliance_and_standards.get("compliance_requirements")
        )

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
                key=lambda s: str(s.get("standard_name") or s.get("standard") or "").lower(),
            )
            for s in items:
                row = table.add_row().cells
                row[0].text = str(s.get("standard_name") or s.get("standard") or "")
                row[1].text = str(s.get("standard_body", ""))
                row[2].text = str(s.get("clause_reference", ""))
                _set_cell_bullets(row[3], s.get("applicability") or s.get("description"))
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
                key=lambda r: str(r.get("regulation_name") or r.get("name") or r.get("id") or "").lower(),
            )
            for r in items:
                row = table.add_row().cells
                row[0].text = str(r.get("regulation_name") or r.get("name") or r.get("id") or "")
                row[1].text = str(r.get("jurisdiction", ""))
                _set_cell_bullets(row[2], r.get("requirement_description") or r.get("description"))
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
    """Risk Register. One table: ID, Category, Likelihood, Impact,
    Description, Mitigation, Owner, Status. Ordered by id.

    "description"/"likelihood"/"mitigation" are the $defs.risk schema's own
    key names. A live model instead used "risk_description"/"probability"/
    "mitigation_strategy" throughout -- confirmed directly against a real
    generated document, where every row's Description/Likelihood/
    Mitigation cell was blank or a bare "—" despite the real content being
    present under those synonym keys. "owner"/"status" are also real
    schema fields that previously had no column at all, silently dropping
    real content (e.g. "Security Team" / "open") that had nowhere to go
    once risk_register's whole key was marked consumed."""
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

        headers = ["ID", "Category", "Likelihood", "Impact", "Description", "Mitigation", "Owner", "Status"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)

        for r in items:
            row = table.add_row().cells
            row[0].text = str(r.get("id", ""))
            row[1].text = str(r.get("category", ""))
            row[2].text = str(r.get("likelihood") or r.get("probability") or "").title()
            row[3].text = str(r.get("impact", "")).title()
            _set_cell_bullets(row[4], r.get("description") or r.get("risk_description"))
            _set_cell_bullets(row[5], r.get("mitigation") or r.get("mitigation_strategy"))
            row[6].text = str(r.get("owner", ""))
            row[7].text = str(r.get("status", "")).replace("_", " ").title()

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
    """Like doc_structure._add_bullet, but with an arbitrary indent depth."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.left_indent = Inches(indent_inches)
    p.add_run(f"• {text}")


def _add_bulleted_group(doc: docx.Document, label: str, values, indent_inches: float) -> None:
    """A bold 'Label:' line followed by one bullet per item. No-op if
    `values` is empty.

    architecture_analysis's own schema says strengths/weaknesses/risks are
    each an ARRAY of strings, but a live model sometimes collapses one
    into a single descriptive sentence instead. Iterating a bare string
    directly (the old `for v in (values or [])` did exactly this) doesn't
    raise -- Python iterates a string's individual CHARACTERS, each of
    which passes `isinstance(v, str) and v.strip()`, so real prose like
    "High availability..." rendered as dozens of one-character bullets
    ("H", "i", "g", "h", ...). Confirmed directly against a real generated
    document. Treating a plain string as a single-item list fixes it
    without discarding the content."""
    if isinstance(values, str):
        values = [values] if values.strip() else []
    else:
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
    """Architecture Analysis -- description/strengths/weaknesses/risks of
    an architectural approach, any alternatives considered on the same
    basis, and a recommendation. Deliberately not an ADR-style rendering
    (no status/date/decided_by -- the generating agent has no real
    meeting to draw on, so nothing here is fabricated as one)."""
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


def _add_architecture_decisions_section(
    doc: docx.Document, architecture_decisions, heading: str = "5.2 Architecture Decisions",
) -> bool:
    """Architecture Decision Records -- one per real recommendation reached
    in architecture_analysis above, persisted so a reader can trace WHY a
    choice was made, not just WHAT exists. Deliberately has no status/
    date/decided-by column: design_document_schema.json's own comment on
    its earlier, removed "architecture_rationale"/decisionRecord field
    documents that giving the generating agent one produced fabricated
    decision-meeting content, so the schema simply carries no such field
    for this renderer to show."""
    try:
        items = [d for d in (architecture_decisions or []) if isinstance(d, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=2)
        doc.add_paragraph(
            "The following records the key architectural decisions made for this "
            "design, the alternatives considered, and the consequences each one "
            "commits the design to."
        )

        items = sorted(items, key=lambda d: _natural_sort_key(d.get("id")))

        for item in items:
            decision_id = item.get("id")
            title = item.get("title") or "Decision"
            heading_text = f"{decision_id}: {title}" if decision_id else str(title)
            doc.add_heading(heading_text, level=3)

            context = item.get("context")
            if context:
                p = doc.add_paragraph()
                p.add_run("Context: ").bold = True
                p.add_run(str(context))

            decision = item.get("decision")
            if decision:
                p = doc.add_paragraph()
                p.add_run("Decision: ").bold = True
                p.add_run(str(decision))

            alternatives = [
                a for a in (item.get("alternatives_considered") or []) if isinstance(a, dict)
            ]
            if alternatives:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(6)
                p.add_run("Alternatives Considered:").bold = True
                for alt in alternatives:
                    option = alt.get("option") or "Alternative"
                    rejected_because = alt.get("rejected_because")
                    text = f"{option} -- rejected because {rejected_because}" if rejected_because else str(option)
                    _bullet_at(doc, text, indent_inches=0.0)

            consequences = item.get("consequences")
            if consequences:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(6)
                p.add_run("Consequences: ").bold = True
                p.add_run(str(consequences))

            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


def _add_viewpoints_and_views_section(
    doc: docx.Document, viewpoints, views, level: int = 2, system_name: str = None, high_level_design: dict = None,
) -> bool:
    """Architecture viewpoints and the views that realize them (ISO/IEC/
    IEEE 42010). Each view is grouped under the viewpoint it declares via
    its own viewpoint-reference field (matched against each viewpoint's
    own name, case/whitespace-insensitive), so a reader sees WHY a view
    exists (its viewpoint's own concerns/stakeholders) directly alongside
    WHAT the view documents, rather than two independently rendered,
    uncorrelated lists -- confirmed as a real gap via a live-generated
    document, where Viewpoints and Views rendered as two separate generic
    tables with no structural link between them even though the schema's
    own cross-reference field exists precisely to express it.

    design_document_schema.json's own template uses "viewpoint_name"/
    "concerns_addressed"/"stakeholders_addressed"/"view_name"/
    "viewpoint_ref", but a live model instead used the shorter "name"/
    "concerns"/"stakeholders"/"name"/"viewpoint" for the exact same
    content -- confirmed directly against a real generated document,
    where this function's FIRST version (checking only the schema's own
    verbose key names) found nothing at all: every viewpoint rendered as
    a bare "Viewpoint" placeholder heading with no description/concerns/
    stakeholders, and every view fell through to "Other Views" since no
    viewpoint_ref ever matched. Every field below tries both shapes.

    A view whose viewpoint reference doesn't match any known viewpoint
    (or is missing/misspelled) still renders in full, grouped under a
    trailing "Other Views" heading -- a broken cross-reference never means
    the view's own content is silently dropped."""
    try:
        viewpoints = [v for v in (viewpoints or []) if isinstance(v, dict)]
        views = [v for v in (views or []) if isinstance(v, dict)]
        if not viewpoints and not views:
            return False

        heading_level = min(max(level, 1), 6)
        sub_level = min(heading_level + 1, 6)

        def _norm(value) -> str:
            return str(value or "").strip().lower()

        def _viewpoint_name(vp: dict):
            return vp.get("viewpoint_name") or vp.get("name")

        def _view_name(view: dict):
            return view.get("view_name") or view.get("name")

        def _view_ref(view: dict):
            return view.get("viewpoint_ref") or view.get("viewpoint")

        viewpoint_name_by_key = {
            _norm(_viewpoint_name(vp)): _viewpoint_name(vp)
            for vp in viewpoints if _viewpoint_name(vp)
        }
        views_by_viewpoint: dict = {}
        unmapped_views = []
        for view in views:
            ref = _norm(_view_ref(view))
            matched_name = viewpoint_name_by_key.get(ref) if ref else None
            if matched_name:
                views_by_viewpoint.setdefault(matched_name, []).append(view)
            else:
                unmapped_views.append(view)

        if viewpoints:
            doc.add_heading("Viewpoints", level=heading_level)
        for vp in viewpoints:
            name = _viewpoint_name(vp) or "Viewpoint"
            doc.add_heading(str(name), level=sub_level)

            description = vp.get("description")
            if description:
                doc.add_paragraph(str(description))

            for fields, label in (
                (("concerns_addressed", "concerns"), "Concerns Addressed"),
                (("stakeholders_addressed", "stakeholders"), "Stakeholders Addressed"),
            ):
                value = next((vp.get(f) for f in fields if vp.get(f)), None)
                _add_bulleted_group(doc, label, value, indent_inches=0.0)

            standard = vp.get("applicable_standard") or vp.get("standard")
            if standard:
                p = doc.add_paragraph()
                p.add_run("Applicable Standard: ").bold = True
                p.add_run(str(standard))

            own_views = views_by_viewpoint.get(name, [])
            if own_views:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(8)
                p.add_run("Views realizing this viewpoint:").bold = True
                for view in own_views:
                    _add_view_entry(
                        doc, view, level=sub_level + 1, system_name=system_name, high_level_design=high_level_design,
                    )

            doc.add_paragraph()

        if unmapped_views:
            doc.add_heading("Other Views", level=heading_level)
            doc.add_paragraph(
                "The following views did not reference one of the viewpoints defined above."
            )
            for view in unmapped_views:
                _add_view_entry(
                    doc, view, level=sub_level, system_name=system_name, high_level_design=high_level_design,
                )
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# Keyword -> real, already-existing high_level_design data most views
# with that kind of name are actually describing. Confirmed as a real
# gap via a live-generated document: a generating agent never populates
# views[].elements/diagrams on the view itself, so EVERY view fell
# through to the honest-but-unhelpful fallback note, even for a "Logical
# View"/"Deployment View" whose own content already exists elsewhere in
# the same design JSON (components/integration_points, deployment_
# topology.environments) and is ALREADY drawn once for the overall
# "Architecture Flow Diagram". This is never fabrication -- it only
# chooses WHICH of that real data to visualize for a given view, the
# same "dispatch by data shape, not by an unreliable tag" principle
# generate_uml_diagram's own docstring already explains for diagram_type.
# A view whose own name/purpose doesn't match any of these (e.g. a
# "Process View" describing a sequence of events, for which no
# high_level_design-level data source exists) still gets the honest
# fallback note -- this is a short, deliberately conservative list, not
# a guess-anything heuristic.
_VIEW_NAME_TO_HLD_CONTEXT_KEYWORDS = (
    (("deployment", "topology", "infrastructure", "physical"), "deployment"),
    (("logical", "component", "integration"), "logical"),
)


def _infer_view_context_from_high_level_design(view: dict, high_level_design: dict):
    """Returns a context dict generate_uml_diagram can draw a real diagram
    from, inferred from the view's own name/description keywords, or None
    if nothing in high_level_design plausibly matches."""
    if not isinstance(high_level_design, dict) or not high_level_design:
        return None

    haystack = f"{view.get('view_name') or view.get('name') or ''} {view.get('description') or ''}".lower()

    for keywords, kind in _VIEW_NAME_TO_HLD_CONTEXT_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            if kind == "deployment":
                environments = (high_level_design.get("deployment_topology") or {}).get("environments")
                if environments:
                    return {"environments": environments}
            elif kind == "logical":
                integration_points = high_level_design.get("integration_points")
                if integration_points:
                    return {"integration_points": integration_points}
    return None


def _add_view_entry(
    doc: docx.Document, view: dict, level: int = 4, system_name: str = None, high_level_design: dict = None,
) -> None:
    """A single view: name (a real heading, not just a bold run -- matches
    the rest of this document's own heading hierarchy, confirmed as a
    real readability gap via a live-generated document), description, and
    -- if the view's own schema fields support it -- a REAL generated
    diagram, not just a text label. Tries, in order:
      1. An explicit diagrams[] descriptor list (the schema's own field
         for this, rendered the same way every other diagram descriptor
         in this document is).
      2. Auto-generating a node-grid diagram directly from the view's own
         elements[] list (generate_uml_diagram's existing "elements ->
         node grid" branch -- no new diagram-drawing code needed).
      3. Inferring, from the view's own name/description, which of
         high_level_design's ALREADY-REAL data (components/integration_
         points, deployment_topology.environments) it's actually
         describing, and drawing THAT -- see
         _infer_view_context_from_high_level_design.
    If none of these apply, no diagram (and no placeholder note) renders
    for this view -- confirmed via direct user feedback that a cluster of
    "[Diagram not yet generated]" notes across several views in the same
    short section reads as broken/unfinished, not honest. The view's own
    name/description are real content and still always render regardless."""
    heading_level = min(max(level, 1), 6)
    name = view.get("view_name") or view.get("name") or "View"
    doc.add_heading(str(name), level=heading_level)

    description = view.get("description")
    if description:
        doc.add_paragraph(str(description))

    diagrams = [d for d in (view.get("diagrams") or []) if isinstance(d, dict)]
    if diagrams:
        for d in diagrams:
            _render_diagram_descriptor(doc, d, level=min(heading_level + 1, 6), context=view, system_name=system_name)
        return

    diagram_path = generate_uml_diagram(view, view, system_name=system_name)
    if not diagram_path:
        inferred_context = _infer_view_context_from_high_level_design(view, high_level_design)
        if inferred_context:
            diagram_path = generate_uml_diagram(view, inferred_context, system_name=system_name)

    if diagram_path and os.path.exists(diagram_path):
        doc.add_picture(diagram_path, width=Inches(5.5))
        doc.add_paragraph()
    # No "[Diagram not yet generated]" placeholder note here -- confirmed
    # via direct user feedback that a cluster of these (one per view with
    # no diagram, several views in the same short section) reads as
    # broken/unfinished rather than honest, unlike the single-diagram
    # case elsewhere in this document (_render_diagram_descriptor's own
    # fallback) that this was originally modeled on. The view's own
    # name/description above is real content either way and is never
    # dropped -- only the empty placeholder for a diagram that doesn't
    # exist is omitted.


def _add_hld_components_section(doc: docx.Document, components, heading: str = "Components", level: int = 3) -> bool:
    """high_level_design.components -- each rendered with a FIXED,
    consistent field order (Type, Owner, Technology Stack, Interfaces,
    Dependencies) regardless of the order fields happen to appear in the
    source JSON. Confirmed as a real readability bug via a live-generated
    document: the generic fallback renderer this replaced showed each
    component's OWN JSON key order, so "Dependencies" rendered as the
    very FIRST line for one component (whichever key the agent happened
    to emit second) and didn't appear at all for a sibling component with
    none -- a reader comparing several components side by side had no
    stable place to look for any given field."""
    try:
        components = [c for c in (components or []) if isinstance(c, dict)]
        if not components:
            return False

        heading_level = min(max(level, 1), 6)
        sub_level = min(heading_level + 1, 6)

        doc.add_heading(heading, level=heading_level)
        for c in components:
            name = c.get("component_name") or c.get("name") or "Component"
            doc.add_heading(str(name), level=sub_level)

            description = c.get("description")
            if description:
                doc.add_paragraph(str(description))

            for field, label in (("type", "Type"), ("owner", "Owner")):
                value = c.get(field)
                if value:
                    p = doc.add_paragraph()
                    p.add_run(f"{label}: ").bold = True
                    p.add_run(str(value))

            for field, label in (
                ("technology_stack", "Technology Stack"),
                ("interfaces", "Interfaces"),
                ("dependencies", "Dependencies"),
            ):
                _add_bulleted_group(doc, label, c.get(field), indent_inches=0.0)

            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


def _add_integration_points_table(
    doc: docx.Document, integration_points, heading: str = "Integration Points", level: int = 3,
) -> bool:
    """high_level_design.integration_points -- same few fields repeated
    per entry (Source, Target, Integration Pattern, Protocol,
    Description), so a table reads it far more clearly at a glance than
    the generic fallback's own repeated bold-label prose blocks did,
    matching how every other similarly-shaped list in this document
    (Requirements, External Systems, Risk Register) already renders."""
    try:
        items = [i for i in (integration_points or []) if isinstance(i, dict)]
        if not items:
            return False

        heading_level = min(max(level, 1), 6)
        doc.add_heading(heading, level=heading_level)

        candidate_cols = [
            ("source", "Source"),
            ("target", "Target"),
            ("integration_pattern", "Integration Pattern"),
            ("protocol", "Protocol"),
            ("description", "Description"),
        ]

        def _value(item: dict, key: str):
            # "source_component"/"target_component" is a confirmed
            # real synonym the design agent sometimes invents by analogy
            # with component_name -- same fallback generate_uml_diagram's
            # own integration_points branch already applies.
            return item.get(key) or item.get(f"{key}_component")

        present_cols = [col for col in candidate_cols if any(_value(item, col[0]) for item in items)] or [candidate_cols[0]]

        table = doc.add_table(rows=1, cols=len(present_cols))
        _set_header_row(table, [label for _, label in present_cols])
        for item in items:
            row = table.add_row().cells
            for idx, (key, _) in enumerate(present_cols):
                row[idx].text = str(_value(item, key) or "")
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()

        data_flow_overviews = [item.get("data_flow_overview") for item in items if item.get("data_flow_overview")]
        if data_flow_overviews:
            p = doc.add_paragraph()
            p.add_run("Data Flow Overview: ").bold = True
            p.add_run(" ".join(str(v) for v in data_flow_overviews))
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


def _add_technology_stack_table(
    doc: docx.Document, technology_stack, heading: str = "Technology Stack", level: int = 3,
) -> bool:
    """high_level_design.technology_stack -- the same 5 fields
    (Technology, Category, Version, License, Justification) repeated per
    entry, exactly the shape a table presents far more scannably than
    the generic fallback's own repeated bold-label prose blocks."""
    try:
        items = [t for t in (technology_stack or []) if isinstance(t, dict)]
        if not items:
            return False

        heading_level = min(max(level, 1), 6)
        doc.add_heading(heading, level=heading_level)

        candidate_cols = [
            ("technology", "Technology"),
            ("category", "Category"),
            ("version", "Version"),
            ("license", "License"),
            ("justification", "Justification"),
        ]
        present_cols = [col for col in candidate_cols if any(item.get(col[0]) for item in items)] or [candidate_cols[0]]

        table = doc.add_table(rows=1, cols=len(present_cols))
        _set_header_row(table, [label for _, label in present_cols])
        for item in items:
            row = table.add_row().cells
            for idx, (key, _) in enumerate(present_cols):
                row[idx].text = str(item.get(key, ""))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# PART II: LOW-LEVEL DESIGN
# ============================================================

def _component_name(component: dict) -> str:
    # "component_name" is the schema's own key (required on every
    # low_level_design.components[] entry). "hld_component_name" is a
    # live model's own invented key -- confirmed directly against a real
    # generated document, where every single LLD component used it
    # instead, leaving every LLD component heading/cell a bare
    # "Component" fallback since neither "component_name" nor "name" ever
    # matched.
    return str(
        component.get("component_name")
        or component.get("hld_component_name")
        or component.get("name")
        or "Component"
    )


def _add_low_level_design_section(
    doc: docx.Document, low_level_design: dict, heading: str = "12.0 Low-Level Design",
    system_name: str = None, has_hld_companion: bool = False,
) -> bool:
    """Low-Level Design, grouped by design discipline (runtime flows,
    component design, interfaces, configuration, operations, and
    optionally detailed engineering constructs) rather than repeated in
    full for every component:
      N.1 Runtime Processing and Sequence Flows
      N.2 Component Design (+ Data Design, for database_design)
      N.3 Interface Design
      N.4 Configuration Design
      N.5 Operational Design
      N.6 Detailed Engineering Design -- optional, only rendered if the
          source content goes beyond architecture-level detail.

    Field names beyond design_document_schema.json's formal componentSpec
    are read defensively via .get() with plausible alternate spellings,
    since the generating agent may elaborate components with additional
    LLD-specific fields the strict schema doesn't enumerate.

    `has_hld_companion`: this section is the sole content of a standalone
    Low-Level Design document (see generation.py's _build_lld_document).
    When a High-Level Design document is ALSO being produced in the same
    call, the intro paragraph points the reader to it; otherwise it
    describes this document's own organization without assuming one
    exists.
    """
    try:
        if not isinstance(low_level_design, dict) or not low_level_design:
            return False

        components = [c for c in (low_level_design.get("components") or []) if isinstance(c, dict)]
        database_design = low_level_design.get("database_design")
        interface_contracts = [
            i for i in (low_level_design.get("interface_contracts") or []) if isinstance(i, dict)
        ]
        detailed_sequence_flows = [
            s for s in (low_level_design.get("detailed_sequence_flows") or []) if isinstance(s, dict)
        ]
        exception_handling_strategy = low_level_design.get("exception_handling_strategy")

        if not any([components, database_design, interface_contracts,
                    detailed_sequence_flows, exception_handling_strategy]):
            return False

        lead = _leading_number(heading, default=12)

        doc.add_heading(heading, level=1)
        if has_hld_companion:
            doc.add_paragraph(
                "This document elaborates the system's High-Level Design -- "
                "published as a separate companion document -- into "
                "implementation-ready detail, organised by design discipline -- "
                "runtime behaviour, component design, interfaces, configuration, "
                "and operations -- so a reviewer interested in one discipline can "
                "find it in one place rather than across every component section."
            )
        else:
            doc.add_paragraph(
                "This document presents the Low-Level Design: implementation-ready "
                "detail for this system, organised by design discipline -- runtime "
                "behaviour, component design, interfaces, configuration, and "
                "operations -- so a reviewer interested in one discipline can find "
                "it in one place rather than across every component section."
            )

        subsection = 1
        rendered_any = False

        # ---- N.1 Runtime Processing and Sequence Flows ----
        component_flows = [
            (_component_name(c), flow)
            for c in components
            for flow in (c.get("sequence_flows") or [])
            if isinstance(flow, dict)
        ]
        if detailed_sequence_flows or component_flows:
            doc.add_heading(f"{lead}.{subsection} Runtime Processing and Sequence Flows", level=2)
            subsection += 1
            doc.add_paragraph(
                "The following sequence flows describe how this design's components "
                "interact at runtime to fulfil its key scenarios."
            )
            for flow in detailed_sequence_flows:
                _render_diagram_descriptor(
                    doc, flow, level=3, context=low_level_design, system_name=system_name
                )
            for name, flow in component_flows:
                _render_diagram_descriptor(
                    doc, flow, level=3, context={"component_name": name}, system_name=system_name
                )
            rendered_any = True

        # ---- N.2 Component Design (+ Data Design) ----
        if components or database_design:
            doc.add_heading(f"{lead}.{subsection} Component Design", level=2)
            subsection += 1
            doc.add_paragraph(
                "The following describes each component's purpose, responsibilities, "
                "dependencies, key design decisions, and scope and operational boundaries."
            )
            for c in sorted(components, key=lambda c: _natural_sort_key(_component_name(c))):
                doc.add_heading(_component_name(c), level=3)
                description = c.get("description")
                if description:
                    doc.add_paragraph(str(description))
                _add_bulleted_group(doc, "Responsibilities", c.get("responsibilities"), indent_inches=0.0)
                _add_bulleted_group(doc, "Dependencies", c.get("dependencies"), indent_inches=0.0)
                _add_bulleted_group(
                    doc, "Key Design Decisions",
                    c.get("key_design_decisions") or c.get("design_decisions"), indent_inches=0.0,
                )
                scope = c.get("scope_and_operational_boundaries") or c.get("scope_and_boundaries")
                if scope:
                    _add_prose_field(doc, "Scope and Operational Boundaries", _stringify_nested(scope))
                _add_bulleted_group(doc, "Technology Stack", c.get("technology_stack"), indent_inches=0.0)
                owner = c.get("owner")
                if owner:
                    _add_prose_field(doc, "Owner", str(owner))
                doc.add_paragraph()

            if isinstance(database_design, dict) and database_design:
                doc.add_heading("Data Design", level=3)
                _render_generic_value(doc, database_design, system_name=system_name)

            rendered_any = True

        # ---- N.3 Interface Design ----
        component_interfaces = [
            (_component_name(c), iface)
            for c in components
            for iface in (c.get("interfaces") or c.get("api_specifications") or [])
            if isinstance(iface, dict)
        ]
        if interface_contracts or component_interfaces:
            doc.add_heading(f"{lead}.{subsection} Interface Design", level=2)
            subsection += 1
            doc.add_paragraph(
                "The following interfaces are exposed or consumed by this design's components."
            )

            headers = ["Interface", "Owning Component", "Protocol", "Authentication", "Error Handling"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for owner_name, iface in [(None, i) for i in interface_contracts] + component_interfaces:
                row = table.add_row().cells
                row[0].text = str(iface.get("interface_name") or iface.get("name") or "")
                row[1].text = str(owner_name or "—")
                row[2].text = str(iface.get("protocol") or "")
                row[3].text = str(iface.get("authentication") or "")
                _set_cell_bullets(row[4], iface.get("error_handling"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

            rendered_any = True

        # ---- N.4 Configuration Design ----
        config_by_component = [
            (_component_name(c), c.get("configuration_parameters") or c.get("configuration"))
            for c in components
            if c.get("configuration_parameters") or c.get("configuration")
        ]
        if config_by_component:
            doc.add_heading(f"{lead}.{subsection} Configuration Design", level=2)
            subsection += 1
            doc.add_paragraph(
                "The following consolidates the key configuration parameters for each component."
            )
            for name, config in config_by_component:
                doc.add_heading(name, level=3)
                _render_generic_value(doc, config, system_name=system_name)

            rendered_any = True

        # ---- N.5 Operational Design ----
        _OPERATIONAL_FIELDS = (
            "logging_and_monitoring", "monitoring", "logging", "alerting",
            "capacity_limits", "error_handling", "recovery_behaviour", "recovery_behavior",
        )
        ops_by_component = []
        for c in components:
            ops_fields = {k: c[k] for k in _OPERATIONAL_FIELDS if c.get(k)}
            if ops_fields:
                ops_by_component.append((_component_name(c), ops_fields))

        if ops_by_component or exception_handling_strategy:
            doc.add_heading(f"{lead}.{subsection} Operational Design", level=2)
            subsection += 1
            doc.add_paragraph(
                "The following consolidates monitoring, logging, alerting, capacity, "
                "and error-recovery behaviour across this design's components."
            )
            if exception_handling_strategy:
                _add_prose_field(
                    doc, "Exception Handling Strategy", _stringify_nested(exception_handling_strategy)
                )
                doc.add_paragraph()
            for name, ops_fields in ops_by_component:
                doc.add_heading(name, level=3)
                _render_generic_value(doc, ops_fields, system_name=system_name)

            rendered_any = True

        # ---- N.6 Detailed Engineering Design (optional) ----
        _ENGINEERING_FIELDS = (
            "class_design", "class_diagrams", "pseudocode",
            "algorithm_details", "unit_test_strategy", "internal_modules",
        )
        engineering_by_component = []
        for c in components:
            eng_fields = {k: c[k] for k in _ENGINEERING_FIELDS if c.get(k)}
            if eng_fields:
                engineering_by_component.append((_component_name(c), eng_fields))

        if engineering_by_component:
            doc.add_heading(f"{lead}.{subsection} Detailed Engineering Design", level=2)
            subsection += 1
            doc.add_paragraph(
                "This section is included only where the source content goes beyond "
                "architecture-level detail into concrete engineering constructs. It "
                "supports engineering implementation rather than architecture "
                "governance review, and can be skipped by reviewers focused on the latter."
            )
            for name, eng_fields in engineering_by_component:
                doc.add_heading(name, level=3)
                _render_generic_value(doc, eng_fields, system_name=system_name)

            rendered_any = True

        return rendered_any

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# OPERATIONAL READINESS
# ============================================================

def _add_operational_readiness_section(
    doc: docx.Document, operational_readiness: dict, heading: str = "10.0 Operational Readiness",
) -> bool:
    """Operational Readiness -- ownership/support/escalation/monitoring/
    alerting for running this design day-to-day, plus any runbooks. A
    design that only names failure modes (risk_register/
    risks_and_mitigations) with no response model for them is not
    actually operationally ready; this section is where that response
    model lives. No-ops on an empty/absent dict -- same convention as
    every other optional top-level design section here."""
    try:
        if not isinstance(operational_readiness, dict) or not operational_readiness:
            return False

        fields = (
            operational_readiness.get("support_model"),
            operational_readiness.get("escalation_path"),
            operational_readiness.get("monitoring_strategy"),
            operational_readiness.get("alerting_strategy"),
            operational_readiness.get("maintenance_activities"),
            operational_readiness.get("runbooks"),
        )
        ownership = operational_readiness.get("ownership")
        if not any(fields) and not (isinstance(ownership, dict) and any(ownership.values())):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section describes how this design is owned, supported, and "
            "monitored once in operation, and the runbooks available for "
            "responding to its known failure modes."
        )

        if isinstance(ownership, dict) and any(ownership.values()):
            team = ownership.get("team")
            contact = ownership.get("contact")
            p = doc.add_paragraph()
            p.add_run("Ownership: ").bold = True
            p.add_run(", ".join(str(v) for v in (team, contact) if v) or "—")

        for key, label in (
            ("support_model", "Support Model"),
            ("escalation_path", "Escalation Path"),
            ("monitoring_strategy", "Monitoring Strategy"),
            ("alerting_strategy", "Alerting Strategy"),
        ):
            value = operational_readiness.get(key)
            if value:
                p = doc.add_paragraph()
                p.add_run(f"{label}: ").bold = True
                p.add_run(str(value))

        _add_bulleted_group(doc, "Maintenance Activities", operational_readiness.get("maintenance_activities"), indent_inches=0.0)

        runbooks = [r for r in (operational_readiness.get("runbooks") or []) if isinstance(r, dict)]
        if runbooks:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.add_run("Runbooks").bold = True

            headers = ["Title", "Trigger", "Reference"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for rb in runbooks:
                row = table.add_row().cells
                row[0].text = str(rb.get("title", ""))
                row[1].text = str(rb.get("trigger", ""))
                row[2].text = str(rb.get("reference", "") or "—")
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


def _add_review_governance_checklist_section(
    doc: docx.Document, review_and_governance: dict, heading: str = "19.0 Review and Governance",
) -> bool:
    """review_and_governance's "sign_off_criteria"/"reconsideration_triggers"
    only -- NOT review_history/change_log/approval_workflow, which describe
    events (reviews, approvals) that have not happened yet and are
    deliberately left unrendered elsewhere to avoid displaying fabricated
    reviewer names/dates. sign_off_criteria/reconsideration_triggers are
    forward-looking design statements (what a reviewer would check, what
    would make this design worth revisiting), not a record of an event,
    so they are real, groundable content with nothing to fabricate."""
    try:
        if not isinstance(review_and_governance, dict) or not review_and_governance:
            return False

        sign_off = [s for s in (review_and_governance.get("sign_off_criteria") or []) if isinstance(s, str) and s.strip()]
        triggers = [s for s in (review_and_governance.get("reconsideration_triggers") or []) if isinstance(s, str) and s.strip()]
        if not sign_off and not triggers:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section lists the criteria a reviewer would check before "
            "signing off on this design, and the conditions that would make "
            "this design worth reconsidering."
        )

        _add_bulleted_group(doc, "Sign-Off Criteria", sign_off, indent_inches=0.0)
        _add_bulleted_group(doc, "Reconsideration Triggers", triggers, indent_inches=0.0)

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# GLOSSARY AND REFERENCES
# ============================================================

def _add_glossary_and_references_section(
    doc: docx.Document, glossary_and_references: dict, heading: str = "11.0 Glossary and References",
) -> bool:
    """Glossary and References -- glossary (term/definition table) and
    references (citation table), plus a "List of Figures" index for
    "diagrams" (a master index of diagrams referenced ELSEWHERE in the
    document, not a place to draw one for the first time -- rendered as a
    reference table, never passed to _render_diagram_descriptor)."""
    try:
        if not isinstance(glossary_and_references, dict) or not glossary_and_references:
            return False

        glossary = [g for g in (glossary_and_references.get("glossary") or []) if isinstance(g, dict)]
        references = [r for r in (glossary_and_references.get("references") or []) if isinstance(r, dict)]
        diagrams = [d for d in (glossary_and_references.get("diagrams") or []) if isinstance(d, dict)]

        if not glossary and not references and not diagrams:
            return False

        lead = _leading_number(heading, default=11)

        doc.add_heading(heading, level=1)

        subsection = 1

        if glossary:
            doc.add_heading(f"{lead}.{subsection} Glossary", level=2)
            subsection += 1
            doc.add_paragraph("This glossary defines terms used throughout this document.")

            headers = ["Term", "Definition"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for g in sorted(glossary, key=lambda g: str(g.get("term") or "").lower()):
                row = table.add_row().cells
                row[0].text = str(g.get("term", ""))
                _set_cell_bullets(row[1], g.get("definition"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if references:
            doc.add_heading(f"{lead}.{subsection} References", level=2)
            subsection += 1
            doc.add_paragraph("The following external references were used in the development of this design.")

            headers = ["Title", "Source", "Version"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for r in references:
                row = table.add_row().cells
                title = str(r.get("title", ""))
                url = r.get("url")
                row[0].text = f"{title} ({url})" if url else title
                row[1].text = str(r.get("source") or "")
                row[2].text = str(r.get("version") or "")
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if diagrams:
            doc.add_heading(f"{lead}.{subsection} List of Figures", level=2)
            subsection += 1
            doc.add_paragraph(
                "The following diagrams appear elsewhere in this document, indexed here for reference."
            )

            headers = ["Title", "Type", "Notation"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for d in diagrams:
                row = table.add_row().cells
                row[0].text = str(d.get("title") or d.get("diagram_id") or "")
                row[1].text = str(d.get("diagram_type") or "").replace("_", " ").title()
                row[2].text = str(d.get("notation_standard") or "")
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False
