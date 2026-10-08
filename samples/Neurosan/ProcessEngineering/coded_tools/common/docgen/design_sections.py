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

import re
import traceback

import docx
from docx.shared import Inches, Pt

from coded_tools.common.docgen.structure import (
    apply_iso_table_formatting,
    _set_cell_bullets,
    _leading_number,
)
from coded_tools.common.docgen.content import (
    _render_diagram_descriptor,
    _render_generic_value,
    _stringify_nested,
    _add_prose_field,
)

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
    """3.0 Requirements -- ISO/IEC/IEEE 29148 style. Functional and
    non-functional requirements each get their own opening paragraph and
    a fixed-column, X.X-numbered table (id/priority/description/
    acceptance criteria, plus a category column derived from the
    ISO/IEC 25010 characteristic for non-functional requirements), sorted
    by id then priority."""
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
    system_name: str = None,
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
        doc.add_paragraph(
            "This part elaborates the High-Level Design (Part I) into "
            "implementation-ready detail, organised by design discipline -- "
            "runtime behaviour, component design, interfaces, configuration, "
            "and operations -- so a reviewer interested in one discipline can "
            "find it in one place rather than across every component section."
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
