"""Bespoke, table-driven renderers for TOGAF architecture-artifact sections:
Architecture Vision, Architecture Requirements Specification, Architecture
Principles, Business/Data/Application/Technology Architecture, Opportunities
and Solutions, Migration Planning, Architecture Compliance Assessment, and
Glossary and References. Mirrors design_sections.py's own conventions
exactly: every renderer adds a short opening paragraph, shows a fixed set of
columns, sorts rows for a stable reading order, and returns True/False so
callers can skip page breaks around a silent no-op.

Scope note: see schema/togaf_json.py's own module docstring for which ADM
phases are covered here and which are deliberately out of scope.
"""

import traceback

import docx
from docx.shared import Inches, Pt

from process_toolkit.docgen.structure import apply_iso_table_formatting, _set_cell_bullets, _leading_number
from process_toolkit.docgen.content import _render_diagram_descriptor
from process_toolkit.docgen.design_sections import _natural_sort_key, _bullet_at, _add_bulleted_group


def _set_header_row(table, headers) -> None:
    for idx, label in enumerate(headers):
        table.rows[0].cells[idx].text = label


def _as_integration_points_context(edges) -> dict:
    """Remaps a list of {"source", "target", "protocol"/"description"}
    dicts (application_communications[]/data_flows[]'s own shape) into the
    {"integration_points": [...]} context shape generate_uml_diagram's
    existing edge-graph dispatch branch already understands -- no new
    diagram-drawing code needed, just adapting the context at the call
    site, exactly what _render_diagram_descriptor's own `context`
    parameter is for."""
    points = []
    for e in edges or []:
        if not isinstance(e, dict):
            continue
        points.append({
            "source": e.get("source"),
            "target": e.get("target"),
            "protocol": e.get("protocol") or e.get("description"),
        })
    return {"integration_points": points}


def _as_environments_context(items, name_key: str, sublabel_key: str) -> dict:
    """Remaps a flat list of dicts into the {"environments": [{"name",
    "infrastructure"}, ...]} context shape generate_uml_diagram's existing
    node-grid dispatch branch already understands."""
    environments = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        environments.append({
            "name": item.get(name_key),
            "infrastructure": item.get(sublabel_key),
        })
    return {"environments": environments}


# ============================================================
# ARCHITECTURE VISION
# ============================================================

def _add_architecture_vision_section(
    doc: docx.Document, architecture_vision: dict, heading: str = "1.0 Architecture Vision",
) -> bool:
    """ADM Phase A -- problem/vision statement, business goals/drivers,
    stakeholders, scope, and the risks identified at the vision stage."""
    try:
        if not isinstance(architecture_vision, dict) or not architecture_vision:
            return False

        fields_present = any(
            architecture_vision.get(k) for k in (
                "problem_statement", "vision_statement", "business_goals", "business_drivers",
                "stakeholders", "scope", "key_business_requirements", "risks_and_mitigations",
            )
        )
        if not fields_present:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section states the problem this architecture addresses, the business "
            "goals and drivers behind it, who it concerns, and its scope."
        )

        for key, label in (("problem_statement", "Problem Statement"), ("vision_statement", "Vision Statement")):
            value = architecture_vision.get(key)
            if value:
                p = doc.add_paragraph()
                p.add_run(f"{label}: ").bold = True
                p.add_run(str(value))

        _add_bulleted_group(doc, "Business Goals", architecture_vision.get("business_goals"), indent_inches=0.0)
        _add_bulleted_group(doc, "Business Drivers", architecture_vision.get("business_drivers"), indent_inches=0.0)

        stakeholders = [s for s in (architecture_vision.get("stakeholders") or []) if isinstance(s, dict)]
        if stakeholders:
            doc.add_heading("1.1 Stakeholders", level=2)
            headers = ["Name", "Role", "Concerns"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for s in stakeholders:
                row = table.add_row().cells
                row[0].text = str(s.get("name", ""))
                row[1].text = str(s.get("role", ""))
                _set_cell_bullets(row[2], s.get("concerns"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        scope = architecture_vision.get("scope")
        if isinstance(scope, dict) and any(scope.values()):
            doc.add_heading("1.2 Scope", level=2)
            _add_bulleted_group(doc, "In Scope", scope.get("in_scope"), indent_inches=0.0)
            _add_bulleted_group(doc, "Out of Scope", scope.get("out_of_scope"), indent_inches=0.0)
            _add_bulleted_group(doc, "Constraints", scope.get("constraints"), indent_inches=0.0)
            _add_bulleted_group(doc, "Assumptions", scope.get("assumptions"), indent_inches=0.0)

        _add_bulleted_group(
            doc, "Key Business Requirements", architecture_vision.get("key_business_requirements"),
            indent_inches=0.0,
        )

        risks = [r for r in (architecture_vision.get("risks_and_mitigations") or []) if isinstance(r, dict)]
        if risks:
            doc.add_heading("1.3 Risks and Mitigations", level=2)
            headers = ["ID", "Description", "Mitigation"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for r in sorted(risks, key=lambda r: _natural_sort_key(r.get("id"))):
                row = table.add_row().cells
                row[0].text = str(r.get("id", ""))
                _set_cell_bullets(row[1], r.get("description"))
                _set_cell_bullets(row[2], r.get("mitigation"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# ARCHITECTURE REQUIREMENTS SPECIFICATION
# ============================================================

def _add_requirements_table(doc: docx.Document, items, include_characteristic: bool) -> None:
    headers = (
        ["ID", "Characteristic", "Description", "Target", "Source"]
        if include_characteristic else ["ID", "Description", "Priority", "Source", "Acceptance Criteria"]
    )
    table = doc.add_table(rows=1, cols=len(headers))
    _set_header_row(table, headers)
    for item in sorted(items, key=lambda i: _natural_sort_key(i.get("id"))):
        row = table.add_row().cells
        row[0].text = str(item.get("id", ""))
        if include_characteristic:
            row[1].text = str(item.get("characteristic", ""))
            _set_cell_bullets(row[2], item.get("description"))
            row[3].text = str(item.get("target", ""))
            row[4].text = str(item.get("source", ""))
        else:
            _set_cell_bullets(row[1], item.get("description"))
            row[2].text = str(item.get("priority", ""))
            row[3].text = str(item.get("source", ""))
            _set_cell_bullets(row[4], item.get("acceptance_criteria"))
    apply_iso_table_formatting(table, doc)
    doc.add_paragraph()


def _add_architecture_requirements_section(
    doc: docx.Document, ars: dict, heading: str = "2.0 Architecture Requirements Specification",
) -> bool:
    """A dedicated requirements register distinct from the Architecture
    Vision -- functional/non-functional requirements plus a traceability
    matrix recording which capability/component id(s) satisfy each one."""
    try:
        if not isinstance(ars, dict) or not ars:
            return False

        functional = [r for r in (ars.get("functional_requirements") or []) if isinstance(r, dict)]
        non_functional = [r for r in (ars.get("non_functional_requirements") or []) if isinstance(r, dict)]
        traceability = [t for t in (ars.get("traceability_matrix") or []) if isinstance(t, dict)]
        if not functional and not non_functional and not traceability and not ars.get("constraints") and not ars.get("assumptions"):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section is the formal requirements register this architecture is "
            "designed to satisfy, with a traceability matrix recording which part of "
            "the architecture satisfies each requirement."
        )

        if functional:
            doc.add_heading("2.1 Functional Requirements", level=2)
            _add_requirements_table(doc, functional, include_characteristic=False)

        if non_functional:
            doc.add_heading("2.2 Non-Functional Requirements", level=2)
            _add_requirements_table(doc, non_functional, include_characteristic=True)

        _add_bulleted_group(doc, "Constraints", ars.get("constraints"), indent_inches=0.0)
        _add_bulleted_group(doc, "Assumptions", ars.get("assumptions"), indent_inches=0.0)

        if traceability:
            doc.add_heading("2.3 Traceability Matrix", level=2)
            headers = ["Requirement ID", "Satisfied By"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for t in sorted(traceability, key=lambda t: _natural_sort_key(t.get("requirement_id"))):
                row = table.add_row().cells
                row[0].text = str(t.get("requirement_id", ""))
                _set_cell_bullets(row[1], t.get("satisfied_by"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# ARCHITECTURE PRINCIPLES
# ============================================================

def _add_architecture_principles_section(
    doc: docx.Document, architecture_principles, heading: str = "3.0 Architecture Principles",
) -> bool:
    """Bounded Preliminary-phase equivalent -- one card per principle:
    statement, rationale, implications. Deliberately not a maturity-
    assessment section; see schema/togaf_json.py's own scope note."""
    try:
        items = [p for p in (architecture_principles or []) if isinstance(p, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "The following architecture principles guide the decisions made throughout "
            "this architecture."
        )

        for item in sorted(items, key=lambda p: _natural_sort_key(p.get("id"))):
            principle_id = item.get("id")
            name = item.get("name") or "Principle"
            heading_text = f"{principle_id}: {name}" if principle_id else str(name)
            doc.add_heading(heading_text, level=2)

            statement = item.get("statement")
            if statement:
                p = doc.add_paragraph()
                p.add_run("Statement: ").bold = True
                p.add_run(str(statement))

            rationale = item.get("rationale")
            if rationale:
                p = doc.add_paragraph()
                p.add_run("Rationale: ").bold = True
                p.add_run(str(rationale))

            _add_bulleted_group(doc, "Implications", item.get("implications"), indent_inches=0.0)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# BUSINESS ARCHITECTURE
# ============================================================

def _add_business_architecture_section(
    doc: docx.Document, business_architecture: dict, heading: str = "4.0 Business Architecture",
) -> bool:
    """ADM Phase B, intentionally light -- capabilities, a capability map,
    and value streams."""
    try:
        if not isinstance(business_architecture, dict) or not business_architecture:
            return False

        capabilities = [c for c in (business_architecture.get("capabilities") or []) if isinstance(c, dict)]
        value_streams = [v for v in (business_architecture.get("value_streams") or []) if isinstance(v, dict)]
        diagram = business_architecture.get("capability_map_diagram")
        if not capabilities and not value_streams and not isinstance(diagram, dict):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section describes the business capabilities this architecture realizes."
        )

        if capabilities:
            headers = ["ID", "Name", "Description", "Supports Goals", "Owner"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for c in sorted(capabilities, key=lambda c: _natural_sort_key(c.get("id"))):
                row = table.add_row().cells
                row[0].text = str(c.get("id", ""))
                row[1].text = str(c.get("name", ""))
                _set_cell_bullets(row[2], c.get("description"))
                _set_cell_bullets(row[3], c.get("supports_goals"))
                row[4].text = str(c.get("owner", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if isinstance(diagram, dict) and diagram:
            context = _as_environments_context(capabilities, "name", "description")
            _render_diagram_descriptor(doc, diagram, 2, context=context)

        if value_streams:
            doc.add_heading("4.1 Value Streams", level=2)
            for vs in value_streams:
                name = vs.get("name") or "Value Stream"
                doc.add_heading(str(name), level=3)
                description = vs.get("description")
                if description:
                    doc.add_paragraph(str(description))
                _add_bulleted_group(doc, "Stages", vs.get("stages"), indent_inches=0.0)

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# DATA ARCHITECTURE
# ============================================================

def _add_data_architecture_section(
    doc: docx.Document, data_architecture: dict, heading: str = "5.0 Data Architecture",
) -> bool:
    """ADM Phase C (data half) -- data entities and data flows, strongly
    derivable from the design's own data_flow_overview/database_design
    (referenced, not re-authored, via database_design_ref)."""
    try:
        if not isinstance(data_architecture, dict) or not data_architecture:
            return False

        entities = [e for e in (data_architecture.get("data_entities") or []) if isinstance(e, dict)]
        flows = [f for f in (data_architecture.get("data_flows") or []) if isinstance(f, dict)]
        diagram = data_architecture.get("data_flow_diagram")
        if not entities and not flows and not isinstance(diagram, dict):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section describes the data entities this architecture manages and how "
            "data flows between components."
        )

        if entities:
            doc.add_heading("5.1 Data Entities", level=2)
            headers = ["Name", "Description", "Owner", "Classification"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for e in sorted(entities, key=lambda e: str(e.get("name") or "").lower()):
                row = table.add_row().cells
                row[0].text = str(e.get("name", ""))
                _set_cell_bullets(row[1], e.get("description"))
                row[2].text = str(e.get("owner", ""))
                row[3].text = str(e.get("classification", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if flows:
            doc.add_heading("5.2 Data Flows", level=2)
            headers = ["Source", "Target", "Description"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for f in flows:
                row = table.add_row().cells
                row[0].text = str(f.get("source", ""))
                row[1].text = str(f.get("target", ""))
                _set_cell_bullets(row[2], f.get("description"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if isinstance(diagram, dict) and diagram:
            _render_diagram_descriptor(doc, diagram, 2, context=_as_integration_points_context(flows))

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# APPLICATION ARCHITECTURE
# ============================================================

def _add_application_architecture_section(
    doc: docx.Document, application_architecture: dict, heading: str = "6.0 Application Architecture",
) -> bool:
    """ADM Phase C (application half) -- application components and their
    communications, strongly derivable from design's own components[]."""
    try:
        if not isinstance(application_architecture, dict) or not application_architecture:
            return False

        components = [c for c in (application_architecture.get("application_components") or []) if isinstance(c, dict)]
        communications = [c for c in (application_architecture.get("application_communications") or []) if isinstance(c, dict)]
        diagram = application_architecture.get("application_communication_diagram")
        if not components and not communications and not isinstance(diagram, dict):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section describes the application components realizing this "
            "architecture's business capabilities, and how they communicate."
        )

        if components:
            doc.add_heading("6.1 Application Components", level=2)
            headers = ["Name", "Description", "Realizes Capabilities", "Satisfies Requirements"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for c in sorted(components, key=lambda c: str(c.get("name") or "").lower()):
                row = table.add_row().cells
                row[0].text = str(c.get("name", ""))
                _set_cell_bullets(row[1], c.get("description"))
                _set_cell_bullets(row[2], c.get("realizes_capabilities"))
                _set_cell_bullets(row[3], c.get("satisfies_requirements"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if communications:
            doc.add_heading("6.2 Application Communications", level=2)
            headers = ["Source", "Target", "Protocol", "Description"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for c in communications:
                row = table.add_row().cells
                row[0].text = str(c.get("source", ""))
                row[1].text = str(c.get("target", ""))
                row[2].text = str(c.get("protocol", ""))
                _set_cell_bullets(row[3], c.get("description"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if isinstance(diagram, dict) and diagram:
            _render_diagram_descriptor(doc, diagram, 2, context=_as_integration_points_context(communications))

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# TECHNOLOGY ARCHITECTURE
# ============================================================

def _add_technology_architecture_section(
    doc: docx.Document, technology_architecture: dict, heading: str = "7.0 Technology Architecture",
) -> bool:
    """ADM Phase D -- the technology portfolio, strongly derivable from
    design's own technology_stack/deployment_topology (referenced, not
    re-authored, via deployment_topology_ref)."""
    try:
        if not isinstance(technology_architecture, dict) or not technology_architecture:
            return False

        portfolio = [t for t in (technology_architecture.get("technology_portfolio") or []) if isinstance(t, dict)]
        diagram = technology_architecture.get("technology_portfolio_diagram")
        if not portfolio and not isinstance(diagram, dict):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section lists the technologies this architecture depends on."
        )

        if portfolio:
            headers = ["Category", "Technology", "Version", "Justification"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for t in sorted(portfolio, key=lambda t: str(t.get("category") or "").lower()):
                row = table.add_row().cells
                row[0].text = str(t.get("category", ""))
                row[1].text = str(t.get("technology", ""))
                row[2].text = str(t.get("version", ""))
                _set_cell_bullets(row[3], t.get("justification"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if isinstance(diagram, dict) and diagram:
            context = _as_environments_context(portfolio, "technology", "category")
            _render_diagram_descriptor(doc, diagram, 2, context=context)

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# OPPORTUNITIES AND SOLUTIONS
# ============================================================

def _add_opportunities_and_solutions_section(
    doc: docx.Document, opportunities_and_solutions, heading: str = "8.0 Opportunities and Solutions",
) -> bool:
    """ADM Phase E -- gap analysis. Every gap cites real requirement/design
    ids in "grounded_in"; never invent a gap with no grounding."""
    try:
        items = [g for g in (opportunities_and_solutions or []) if isinstance(g, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section identifies gaps between the current and target architecture "
            "and the solutions proposed to close them."
        )

        headers = ["ID", "Gap", "Grounded In", "Proposed Solution", "Work Package"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for item in sorted(items, key=lambda g: _natural_sort_key(g.get("id"))):
            row = table.add_row().cells
            row[0].text = str(item.get("id", ""))
            _set_cell_bullets(row[1], item.get("gap_description"))
            _set_cell_bullets(row[2], item.get("grounded_in"))
            _set_cell_bullets(row[3], item.get("proposed_solution"))
            row[4].text = str(item.get("work_package_ref", ""))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# MIGRATION PLANNING
# ============================================================

def _add_migration_planning_section(
    doc: docx.Document, migration_planning: dict, heading: str = "9.0 Migration Planning",
) -> bool:
    """ADM Phase F, deliberately LIGHT -- work packages sequenced by
    dependency only. No date/budget/team-capacity fields exist in the
    schema at all (enforced by absence, not by an instruction not to fill
    one in), so there is nothing here for an agent to fabricate."""
    try:
        if not isinstance(migration_planning, dict) or not migration_planning:
            return False

        work_packages = [w for w in (migration_planning.get("work_packages") or []) if isinstance(w, dict)]
        sequencing_notes = migration_planning.get("sequencing_notes")
        if not work_packages and not sequencing_notes:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section sequences the work packages needed to migrate to the target "
            "architecture, by dependency only -- no dates, budget, or team-capacity "
            "figures are stated, since none are available to ground them in."
        )

        for item in sorted(work_packages, key=lambda w: _natural_sort_key(w.get("id"))):
            package_id = item.get("id")
            name = item.get("name") or "Work Package"
            heading_text = f"{package_id}: {name}" if package_id else str(name)
            doc.add_heading(heading_text, level=2)

            description = item.get("description")
            if description:
                doc.add_paragraph(str(description))

            _add_bulleted_group(doc, "Depends On", item.get("depends_on"), indent_inches=0.0)
            _add_bulleted_group(doc, "Delivers", item.get("delivers"), indent_inches=0.0)
            doc.add_paragraph()

        if sequencing_notes:
            p = doc.add_paragraph()
            p.add_run("Sequencing Notes: ").bold = True
            p.add_run(str(sequencing_notes))

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# ARCHITECTURE COMPLIANCE ASSESSMENT
# ============================================================

def _add_architecture_compliance_assessment_section(
    doc: docx.Document, architecture_compliance_assessment: dict,
    heading: str = "10.0 Architecture Compliance Assessment",
) -> bool:
    """ADM Phase G, deliberately LIGHT -- references the design's own
    already-real compliance_and_standards/risk_register by id; never
    fabricates new governance structures."""
    try:
        if not isinstance(architecture_compliance_assessment, dict) or not architecture_compliance_assessment:
            return False

        findings = [
            f for f in (architecture_compliance_assessment.get("compliance_findings") or [])
            if isinstance(f, dict)
        ]
        if not findings:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section records this architecture's compliance against the standards "
            "and requirements already identified elsewhere in its source design/"
            "requirements documentation."
        )

        headers = ["Standard / Requirement", "Status", "Reference"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for f in findings:
            row = table.add_row().cells
            row[0].text = str(f.get("standard_or_requirement", ""))
            row[1].text = str(f.get("status", "")).replace("_", " ").title()
            row[2].text = str(f.get("reference", ""))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()

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
    """Glossary (term/definition table) and references (citation table).
    A small, deliberate duplicate of design_sections.py's own version
    (minus its "diagrams"/List-of-Figures handling and "version" column,
    neither of which this schema's glossary_and_references carries) --
    matching the one-function-per-module, no-cross-imports convention
    requirements_sections.py/proposal_response_sections.py's own
    _add_glossary_section functions already follow."""
    try:
        if not isinstance(glossary_and_references, dict) or not glossary_and_references:
            return False

        glossary = [g for g in (glossary_and_references.get("glossary") or []) if isinstance(g, dict)]
        references = [r for r in (glossary_and_references.get("references") or []) if isinstance(r, dict)]
        if not glossary and not references:
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
            doc.add_paragraph("The following external references were used in the development of this architecture.")

            headers = ["Title", "Source"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for r in references:
                row = table.add_row().cells
                title = str(r.get("title", ""))
                url = r.get("url")
                row[0].text = f"{title} ({url})" if url else title
                row[1].text = str(r.get("source") or "")
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False
