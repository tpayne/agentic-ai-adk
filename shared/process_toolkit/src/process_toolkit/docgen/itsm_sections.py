"""Bespoke, table-driven renderers for ITSM process-document sections:
Service Catalog, Stakeholders and Roles, Incident/Problem/Change Management,
Request Fulfillment, Service Level Management, Configuration Management,
the RACI Matrix, Tooling and Platform, Risks and Controls, and Glossary and
References. Mirrors togaf_sections.py's own conventions exactly: every
renderer adds a short opening paragraph, shows a fixed set of columns,
sorts rows for a stable reading order, and returns True/False so callers
can skip page breaks around a silent no-op.

Scope note: see schema/itsm_json.py's own module docstring for which ITIL
practices are covered here and which are deliberately out of scope.
"""

import traceback

import docx
from docx.shared import Inches, Pt

from process_toolkit.docgen.structure import apply_iso_table_formatting, _set_cell_bullets, _leading_number
from process_toolkit.docgen.content import _render_diagram_descriptor
from process_toolkit.docgen.design_sections import _natural_sort_key, _bullet_at, _add_bulleted_group
from process_toolkit.docgen.togaf_sections import _as_integration_points_context


def _set_header_row(table, headers) -> None:
    for idx, label in enumerate(headers):
        table.rows[0].cells[idx].text = label


def _as_sequential_steps_context(process_steps) -> dict:
    """Remaps a process_steps[] list (step_id/step_name, naturally
    sequential -- no explicit depends_on field in this schema) into the
    {"integration_points": [...]} context shape generate_uml_diagram's
    existing edge-graph dispatch branch already understands, by pairing
    each step with the next one in list order. No new diagram-drawing
    code needed, same adapter-at-the-call-site pattern as togaf_sections.
    py's own _as_integration_points_context/_as_environments_context."""
    steps = [s for s in (process_steps or []) if isinstance(s, dict)]
    points = []
    for current, nxt in zip(steps, steps[1:]):
        source = current.get("step_name") or current.get("step_id")
        target = nxt.get("step_name") or nxt.get("step_id")
        if source and target:
            points.append({"source": source, "target": target, "protocol": None})
    return {"integration_points": points}


def _add_process_steps_table(doc: docx.Document, process_steps) -> bool:
    """Shared table renderer for the four process_steps[] lists (incident/
    problem/change/request_fulfillment all share this exact shape)."""
    steps = [s for s in (process_steps or []) if isinstance(s, dict)]
    if not steps:
        return False
    headers = ["Step ID", "Step Name", "Description", "Responsible Role", "Inputs", "Outputs"]
    table = doc.add_table(rows=1, cols=len(headers))
    _set_header_row(table, headers)
    for s in sorted(steps, key=lambda s: _natural_sort_key(s.get("step_id"))):
        row = table.add_row().cells
        row[0].text = str(s.get("step_id", ""))
        row[1].text = str(s.get("step_name", ""))
        _set_cell_bullets(row[2], s.get("description"))
        row[3].text = str(s.get("responsible_role", ""))
        _set_cell_bullets(row[4], s.get("inputs"))
        _set_cell_bullets(row[5], s.get("outputs"))
    apply_iso_table_formatting(table, doc)
    doc.add_paragraph()
    return True


# ============================================================
# SERVICE CATALOG
# ============================================================

def _add_service_catalog_section(
    doc: docx.Document, service_catalog: dict, heading: str = "1.0 Service Catalog",
) -> bool:
    """The services this ITSM process document governs -- what's being
    supported, not how (that's every later section's job)."""
    try:
        if not isinstance(service_catalog, dict) or not service_catalog:
            return False

        services = [s for s in (service_catalog.get("services") or []) if isinstance(s, dict)]
        if not services:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section lists the services this ITSM process document governs, and "
            "their business criticality."
        )

        headers = ["ID", "Name", "Description", "Category", "Business Criticality", "Owner"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for s in sorted(services, key=lambda s: _natural_sort_key(s.get("id"))):
            row = table.add_row().cells
            row[0].text = str(s.get("id", ""))
            row[1].text = str(s.get("name", ""))
            _set_cell_bullets(row[2], s.get("description"))
            row[3].text = str(s.get("category", ""))
            row[4].text = str(s.get("business_criticality", ""))
            row[5].text = str(s.get("owner", ""))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# STAKEHOLDERS AND ROLES
# ============================================================

def _add_stakeholders_and_roles_section(
    doc: docx.Document, stakeholders_and_roles, heading: str = "2.0 Stakeholders and Roles",
) -> bool:
    """Who is involved in running these processes and at which escalation
    tier -- the RACI Matrix (section 9.0) assigns these same role names to
    specific activities."""
    try:
        items = [r for r in (stakeholders_and_roles or []) if isinstance(r, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section lists the roles involved in running these ITSM processes, and "
            "their escalation tier."
        )

        headers = ["Role", "Responsibilities", "Escalation Tier"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for r in sorted(items, key=lambda r: str(r.get("role") or "").lower()):
            row = table.add_row().cells
            row[0].text = str(r.get("role", ""))
            _set_cell_bullets(row[1], r.get("responsibilities"))
            row[2].text = str(r.get("escalation_tier", ""))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# INCIDENT MANAGEMENT
# ============================================================

def _add_incident_management_section(
    doc: docx.Document, incident_management: dict, heading: str = "3.0 Incident Management",
) -> bool:
    try:
        if not isinstance(incident_management, dict) or not incident_management:
            return False

        priority_matrix = [p for p in (incident_management.get("priority_matrix") or []) if isinstance(p, dict)]
        process_steps = incident_management.get("process_steps")
        diagram = incident_management.get("process_flow_diagram")
        escalation_paths = [e for e in (incident_management.get("escalation_paths") or []) if isinstance(e, dict)]
        if not priority_matrix and not process_steps and not isinstance(diagram, dict) and not escalation_paths:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section defines how incidents are detected, prioritized, and resolved."
        )

        if priority_matrix:
            doc.add_heading("3.1 Priority Matrix", level=2)
            headers = ["Priority", "Impact", "Urgency", "Target Response Time", "Target Resolution Time"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for p in sorted(priority_matrix, key=lambda p: str(p.get("priority") or "")):
                row = table.add_row().cells
                row[0].text = str(p.get("priority", ""))
                row[1].text = str(p.get("impact", ""))
                row[2].text = str(p.get("urgency", ""))
                row[3].text = str(p.get("target_response_time", ""))
                row[4].text = str(p.get("target_resolution_time", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if process_steps:
            doc.add_heading("3.2 Process Flow", level=2)
            _add_process_steps_table(doc, process_steps)

        if isinstance(diagram, dict) and diagram:
            _render_diagram_descriptor(doc, diagram, 2, context=_as_sequential_steps_context(process_steps))

        if escalation_paths:
            doc.add_heading("3.3 Escalation Paths", level=2)
            headers = ["From Tier", "To Tier", "Trigger Condition"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for e in escalation_paths:
                row = table.add_row().cells
                row[0].text = str(e.get("from_tier", ""))
                row[1].text = str(e.get("to_tier", ""))
                _set_cell_bullets(row[2], e.get("trigger_condition"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# PROBLEM MANAGEMENT
# ============================================================

def _add_problem_management_section(
    doc: docx.Document, problem_management: dict, heading: str = "4.0 Problem Management",
) -> bool:
    try:
        if not isinstance(problem_management, dict) or not problem_management:
            return False

        process_steps = problem_management.get("process_steps")
        diagram = problem_management.get("process_flow_diagram")
        known_errors = [k for k in (problem_management.get("known_errors") or []) if isinstance(k, dict)]
        if not process_steps and not isinstance(diagram, dict) and not known_errors:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section defines how problems (the underlying cause of one or more "
            "incidents) are investigated and tracked."
        )

        if process_steps:
            doc.add_heading("4.1 Process Flow", level=2)
            _add_process_steps_table(doc, process_steps)

        if isinstance(diagram, dict) and diagram:
            _render_diagram_descriptor(doc, diagram, 2, context=_as_sequential_steps_context(process_steps))

        if known_errors:
            doc.add_heading("4.2 Known Errors", level=2)
            headers = ["ID", "Description", "Workaround", "Linked Incidents"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for k in sorted(known_errors, key=lambda k: _natural_sort_key(k.get("id"))):
                row = table.add_row().cells
                row[0].text = str(k.get("id", ""))
                _set_cell_bullets(row[1], k.get("description"))
                _set_cell_bullets(row[2], k.get("workaround"))
                _set_cell_bullets(row[3], k.get("linked_incidents"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# CHANGE MANAGEMENT
# ============================================================

def _add_change_management_section(
    doc: docx.Document, change_management: dict, heading: str = "5.0 Change Management",
) -> bool:
    try:
        if not isinstance(change_management, dict) or not change_management:
            return False

        change_types = [c for c in (change_management.get("change_types") or []) if isinstance(c, dict)]
        process_steps = change_management.get("process_steps")
        diagram = change_management.get("process_flow_diagram")
        cab_members = [m for m in (change_management.get("cab_members") or []) if isinstance(m, dict)]
        risk_criteria = [r for r in (change_management.get("risk_assessment_criteria") or []) if isinstance(r, dict)]
        if not change_types and not process_steps and not isinstance(diagram, dict) and not cab_members and not risk_criteria:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section defines how changes are requested, assessed, approved, and "
            "implemented, including the Change Advisory Board (CAB)."
        )

        if change_types:
            doc.add_heading("5.1 Change Types", level=2)
            headers = ["Type", "Description", "Approval Path"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for c in sorted(change_types, key=lambda c: str(c.get("type") or "").lower()):
                row = table.add_row().cells
                row[0].text = str(c.get("type", "")).replace("_", " ").title()
                _set_cell_bullets(row[1], c.get("description"))
                _set_cell_bullets(row[2], c.get("approval_path"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if process_steps:
            doc.add_heading("5.2 Process Flow", level=2)
            _add_process_steps_table(doc, process_steps)

        if isinstance(diagram, dict) and diagram:
            _render_diagram_descriptor(doc, diagram, 2, context=_as_sequential_steps_context(process_steps))

        if cab_members:
            doc.add_heading("5.3 Change Advisory Board Members", level=2)
            headers = ["Role", "Name / Title"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for m in cab_members:
                row = table.add_row().cells
                row[0].text = str(m.get("role", ""))
                row[1].text = str(m.get("name_or_title", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if risk_criteria:
            doc.add_heading("5.4 Risk Assessment Criteria", level=2)
            headers = ["Risk Level", "Criteria", "Required Approvals"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for r in risk_criteria:
                row = table.add_row().cells
                row[0].text = str(r.get("risk_level", ""))
                _set_cell_bullets(row[1], r.get("criteria"))
                _set_cell_bullets(row[2], r.get("required_approvals"))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# REQUEST FULFILLMENT
# ============================================================

def _add_request_fulfillment_section(
    doc: docx.Document, request_fulfillment: dict, heading: str = "6.0 Request Fulfillment",
) -> bool:
    try:
        if not isinstance(request_fulfillment, dict) or not request_fulfillment:
            return False

        request_types = [r for r in (request_fulfillment.get("request_types") or []) if isinstance(r, dict)]
        process_steps = request_fulfillment.get("process_steps")
        diagram = request_fulfillment.get("process_flow_diagram")
        if not request_types and not process_steps and not isinstance(diagram, dict):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section defines how standard service requests (access, provisioning, "
            "information) are fulfilled, distinct from incidents and changes."
        )

        if request_types:
            doc.add_heading("6.1 Request Types", level=2)
            headers = ["Type", "Description", "Target Fulfillment Time"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for r in sorted(request_types, key=lambda r: str(r.get("type") or "").lower()):
                row = table.add_row().cells
                row[0].text = str(r.get("type", ""))
                _set_cell_bullets(row[1], r.get("description"))
                row[2].text = str(r.get("target_fulfillment_time", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if process_steps:
            doc.add_heading("6.2 Process Flow", level=2)
            _add_process_steps_table(doc, process_steps)

        if isinstance(diagram, dict) and diagram:
            _render_diagram_descriptor(doc, diagram, 2, context=_as_sequential_steps_context(process_steps))

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# SERVICE LEVEL MANAGEMENT
# ============================================================

def _add_service_level_management_section(
    doc: docx.Document, service_level_management: dict, heading: str = "7.0 Service Level Management",
) -> bool:
    try:
        if not isinstance(service_level_management, dict) or not service_level_management:
            return False

        slas = [s for s in (service_level_management.get("slas") or []) if isinstance(s, dict)]
        olas = [o for o in (service_level_management.get("olas") or []) if isinstance(o, dict)]
        ucs = [u for u in (service_level_management.get("underpinning_contracts") or []) if isinstance(u, dict)]
        if not slas and not olas and not ucs:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section defines the Service Level Agreements (SLAs) with the business, "
            "the internal Operational Level Agreements (OLAs) that support them, and any "
            "Underpinning Contracts (UCs) with external vendors."
        )

        if slas:
            doc.add_heading("7.1 Service Level Agreements", level=2)
            headers = ["ID", "Service ID", "Metric", "Target", "Measurement Window"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for s in sorted(slas, key=lambda s: _natural_sort_key(s.get("id"))):
                row = table.add_row().cells
                row[0].text = str(s.get("id", ""))
                row[1].text = str(s.get("service_id", ""))
                row[2].text = str(s.get("metric", ""))
                row[3].text = str(s.get("target", ""))
                row[4].text = str(s.get("measurement_window", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if olas:
            doc.add_heading("7.2 Operational Level Agreements", level=2)
            headers = ["ID", "Internal Team", "Metric", "Target"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for o in sorted(olas, key=lambda o: _natural_sort_key(o.get("id"))):
                row = table.add_row().cells
                row[0].text = str(o.get("id", ""))
                row[1].text = str(o.get("internal_team", ""))
                row[2].text = str(o.get("metric", ""))
                row[3].text = str(o.get("target", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if ucs:
            doc.add_heading("7.3 Underpinning Contracts", level=2)
            headers = ["ID", "Vendor", "Scope", "Linked SLA"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for u in sorted(ucs, key=lambda u: _natural_sort_key(u.get("id"))):
                row = table.add_row().cells
                row[0].text = str(u.get("id", ""))
                row[1].text = str(u.get("vendor", ""))
                _set_cell_bullets(row[2], u.get("scope"))
                row[3].text = str(u.get("linked_sla", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# CONFIGURATION MANAGEMENT
# ============================================================

def _add_configuration_management_section(
    doc: docx.Document, configuration_management: dict, heading: str = "8.0 Configuration Management",
) -> bool:
    """Light CMDB -- configuration items and their relationships only; no
    discovery/reconciliation modeling, no lifecycle-state tracking."""
    try:
        if not isinstance(configuration_management, dict) or not configuration_management:
            return False

        cis = [c for c in (configuration_management.get("configuration_items") or []) if isinstance(c, dict)]
        relationships = [r for r in (configuration_management.get("relationships") or []) if isinstance(r, dict)]
        diagram = configuration_management.get("relationship_diagram")
        if not cis and not relationships and not isinstance(diagram, dict):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section lists the configuration items (CIs) this ITSM process document "
            "is aware of, and the relationships between them."
        )

        if cis:
            doc.add_heading("8.1 Configuration Items", level=2)
            headers = ["ID", "Name", "Type", "Owner"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for c in sorted(cis, key=lambda c: _natural_sort_key(c.get("id"))):
                row = table.add_row().cells
                row[0].text = str(c.get("id", ""))
                row[1].text = str(c.get("name", ""))
                row[2].text = str(c.get("type", ""))
                row[3].text = str(c.get("owner", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if relationships:
            doc.add_heading("8.2 Relationships", level=2)
            headers = ["Source CI", "Target CI", "Relationship Type"]
            table = doc.add_table(rows=1, cols=len(headers))
            _set_header_row(table, headers)
            for r in relationships:
                row = table.add_row().cells
                row[0].text = str(r.get("source_ci", ""))
                row[1].text = str(r.get("target_ci", ""))
                row[2].text = str(r.get("relationship_type", ""))
            apply_iso_table_formatting(table, doc)
            doc.add_paragraph()

        if isinstance(diagram, dict) and diagram:
            context = _as_integration_points_context(
                [{"source": r.get("source_ci"), "target": r.get("target_ci"), "description": r.get("relationship_type")} for r in relationships]
            )
            _render_diagram_descriptor(doc, diagram, 2, context=context)

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# RACI MATRIX
# ============================================================

def _add_raci_matrix_section(
    doc: docx.Document, raci_matrix, heading: str = "9.0 RACI Matrix",
) -> bool:
    """Cross-process RACI -- every row names which process area it belongs
    to, so one table covers governance across all of incident/problem/
    change/request/SLM without needing a separate RACI per process."""
    try:
        items = [r for r in (raci_matrix or []) if isinstance(r, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This RACI matrix records who is Responsible, Accountable, Consulted, and "
            "Informed for each key activity across these ITSM processes."
        )

        headers = ["Process Area", "Activity", "Responsible", "Accountable", "Consulted", "Informed"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for r in sorted(items, key=lambda r: (str(r.get("process_area") or "").lower(), str(r.get("activity") or "").lower())):
            row = table.add_row().cells
            row[0].text = str(r.get("process_area", ""))
            _set_cell_bullets(row[1], r.get("activity"))
            row[2].text = str(r.get("responsible", ""))
            row[3].text = str(r.get("accountable", ""))
            row[4].text = str(r.get("consulted", ""))
            row[5].text = str(r.get("informed", ""))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# TOOLING AND PLATFORM
# ============================================================

def _add_tooling_and_platform_section(
    doc: docx.Document, tooling_and_platform, heading: str = "10.0 Tooling and Platform",
) -> bool:
    try:
        items = [t for t in (tooling_and_platform or []) if isinstance(t, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section lists the tooling and platforms these ITSM processes run on."
        )

        headers = ["Category", "Tool Name", "Purpose"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for t in sorted(items, key=lambda t: str(t.get("category") or "").lower()):
            row = table.add_row().cells
            row[0].text = str(t.get("category", ""))
            row[1].text = str(t.get("tool_name", ""))
            _set_cell_bullets(row[2], t.get("purpose"))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()

        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# RISKS AND CONTROLS
# ============================================================

def _add_risks_and_controls_section(
    doc: docx.Document, risks_and_controls, heading: str = "11.0 Risks and Controls",
) -> bool:
    try:
        items = [r for r in (risks_and_controls or []) if isinstance(r, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section records the risks identified against these ITSM processes and "
            "the controls mitigating each one."
        )

        headers = ["Risk", "Control"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for r in items:
            row = table.add_row().cells
            _set_cell_bullets(row[0], r.get("risk"))
            _set_cell_bullets(row[1], r.get("control"))
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
    doc: docx.Document, glossary_and_references: dict, heading: str = "12.0 Glossary and References",
) -> bool:
    """A small, deliberate duplicate of togaf_sections.py's/design_sections.
    py's own version -- matching the one-function-per-module,
    no-cross-imports convention this codebase already follows."""
    try:
        if not isinstance(glossary_and_references, dict) or not glossary_and_references:
            return False

        glossary = [g for g in (glossary_and_references.get("glossary") or []) if isinstance(g, dict)]
        references = [r for r in (glossary_and_references.get("references") or []) if isinstance(r, dict)]
        if not glossary and not references:
            return False

        lead = _leading_number(heading, default=12)
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
            doc.add_paragraph("The following external references were used in the development of these processes.")

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
