# process_agents/helpers/doc_content.py

import docx
import os
from docx.shared import Inches, Pt

import traceback
import logging
from .doc_structure import _add_header, _add_bullet

from ..step_diagram_agent import generate_step_diagram_for_step

logger = logging.getLogger("ProcessArchitect.DocContent")

def _add_overview_section(doc: docx.Document, data: dict) -> None:
    """
    1.0 Process Overview.

    Renders:
    - introduction or description
    - assumptions
    - constraints
    - high-level metadata (purpose, scope, industry_sector) as numbered subheadings
    """
    try:
        doc.add_heading("1.0 Process Overview", level=1)

        # --- Intro / Description ---
        introduction = data.get("introduction")
        description = data.get("description") or data.get("process_description")

        if introduction:
            doc.add_paragraph(str(introduction))
        elif description:
            doc.add_paragraph(str(description))
        else:
            doc.add_paragraph(
                "This section provides a high-level overview of the business process."
            )

        # Track next subsection number
        subsection_number = 1

        # --- Assumptions ---
        assumptions = data.get("assumptions")
        if isinstance(assumptions, list) and assumptions:
            doc.add_heading(f"1.{subsection_number} Assumptions", level=2)
            subsection_number += 1
            for item in assumptions:
                doc.add_paragraph(item, style='List Bullet')

        # --- Constraints ---
        constraints = data.get("constraints")
        if isinstance(constraints, list) and constraints:
            doc.add_heading(f"1.{subsection_number} Constraints", level=2)
            subsection_number += 1
            for item in constraints:
                doc.add_paragraph(item, style='List Bullet')

        # --- High-level metadata as numbered subsections ---
        ordered_metadata = [
            ("purpose", "Purpose"),
            ("scope", "Scope"),
            ("industry_sector", "Industry Sector"),
        ]

        for key, label in ordered_metadata:
            value = data.get(key)
            if value:
                doc.add_heading(f"1.{subsection_number} {label}", level=2)
                subsection_number += 1
                doc.add_paragraph(str(value))

        # --- Remaining metadata (non-numbered key/value pairs) ---
        remaining_keys = [
            "out_of_scope",
            "business_unit",
            "owner",
        ]

        for key in remaining_keys:
            if key in data:
                p = doc.add_paragraph()
                r = p.add_run(f"{key.replace('_', ' ').title()}: ")
                r.bold = True
                p.add_run(str(data.get(key)))

    except Exception:
        traceback.print_exc()
def _add_stakeholders_section(doc: docx.Document, stakeholders) -> None:
    """
    2.0 Stakeholders & Responsibilities.

    Normalized expectation:
    - stakeholders: list of:
        {
          "stakeholder_name": "...",
          "responsibilities": [ "...", "..." ]
        }
    - Fallback: list of strings is also supported.
    """
    try:
        if not stakeholders:
            return
        if not isinstance(stakeholders, list):
            return

        doc.add_heading("2.0 Stakeholders and Responsibilities", level=1)
        doc.add_paragraph(
            f"The following is a list of key stakeholders involved in this process. "
            f"Understanding their roles and responsibilities is crucial for successful implementation."
        )

        # Simple list of strings
        if all(isinstance(s, str) for s in stakeholders):
            for s in stakeholders:
                doc.add_paragraph(str(s), style="List Bullet")
            doc.add_paragraph()
            return

        # List of dicts
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Stakeholder"
        hdr_cells[1].text = "Responsibilities"

        for s in stakeholders:
            if not isinstance(s, dict):
                continue
            name = (
                s.get("stakeholder_name")
                or s.get("role_name")
                or s.get("name")
                or s.get("role")
                or "Stakeholder"
            )
            responsibilities = s.get("responsibilities", [])

            row_cells = table.add_row().cells
            row_cells[0].text = str(name)
            if isinstance(responsibilities, list):
                row_cells[1].text = "\n".join(str(x) for x in responsibilities)
            else:
                row_cells[1].text = str(responsibilities)

        doc.add_paragraph()
    except Exception:
        traceback.print_exc()

def _add_process_steps_section(doc: docx.Document, steps) -> None:
    """
    3.0 Process Steps / Workflow for normalized JSON.

    Normalized expectation:
    - process_steps: list of:
        {
          "step_number": 1,
          "step_name": "...",
          "description": "...",
          "responsible_party": [ "...", "..." ],
          "activities": [ "...", "..." ],
          "inputs": [ "...", "..." ],
          "outputs": [ "...", "..." ],
          "success_criteria": "...",
          "KPIs": [ "...", "..." ],
          "escalation_procedure": "..."
        }
    """
    logger.info("Process sub steps...")
    try:
        if not isinstance(steps, list) or not steps:
            return

        doc.add_heading("3.0 Process Workflow", level=1)
        doc.add_paragraph(
            f"The following is a list of key steps in the process workflow."
        )

        current_step_name = None

        for s_idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue

            step_no = step.get("step_number") or step.get("step_id") or s_idx
            current_step_name = step.get("step_name", f"Step {step_no}") 
            name = current_step_name
            description = step.get("description") or step.get("step_description", "")
            responsible = step.get("responsible_party") or step.get("responsible", "")
            inputs = step.get("inputs") or step.get("input")
            outputs = step.get("outputs") or step.get("output")
            sub_steps = step.get("sub_steps")
            activities = step.get("activities")
            success_criteria = step.get("success_criteria")
            kpis = step.get("KPIs") or step.get("kpis")
            escalation = step.get("escalation_procedure")

            doc.add_heading(f"3.{s_idx} {name}", level=2)

            # Description
            if description:
                _add_header(doc, "Description:")
                _add_bullet(doc, description)

            # Responsible Parties
            if responsible:
                _add_header(doc, "Responsible Parties:")
                if isinstance(responsible, list):
                    for r_item in responsible:
                        _add_bullet(doc, r_item)
                else:
                    _add_bullet(doc, responsible)

            # Inputs
            if inputs:
                _add_header(doc, "Inputs:")
                if isinstance(inputs, list):
                    for i in inputs:
                        _add_bullet(doc, i)
                else:
                    _add_bullet(doc, inputs)

            # Outputs
            if outputs:
                _add_header(doc, "Outputs:")
                if isinstance(outputs, list):
                    for o in outputs:
                        _add_bullet(doc, o)
                else:
                    _add_bullet(doc, outputs)

            # Key Activities
            if activities and isinstance(activities, list):
                _add_header(doc, "Key Activities:")
                for a in activities:
                    _add_bullet(doc, a)

            # Sub-Steps
            if sub_steps and isinstance(sub_steps, list):
                _add_header(doc, "Sub-Steps:")
                for idx_sub, sub in enumerate(sub_steps, start=1):
                    if not isinstance(sub, dict):
                        continue

                    ss_name = sub.get("sub_step_name", f"Sub-step {idx_sub}")
                    ss_desc = sub.get("sub_step_description", "")
                    ss_acts = sub.get("activities", [])

                    h = doc.add_heading(f"3.{s_idx}.{idx_sub} {ss_name}", level=3)
                    h.paragraph_format.space_before = Pt(10)
                    h.paragraph_format.space_after = Pt(0)

                    if ss_desc:
                        p = doc.add_paragraph(str(ss_desc))
                        p.paragraph_format.space_before = Pt(0)
                        p.paragraph_format.space_after = Pt(0)

                    if isinstance(ss_acts, list) and ss_acts:
                        for act in ss_acts:
                            _add_bullet(doc, act)

            # Success Criteria
            if success_criteria:
                _add_header(doc, "Success Criteria:")
                if isinstance(success_criteria, list):
                    for crit in success_criteria:
                        _add_bullet(doc, crit)
                else:
                    _add_bullet(doc, success_criteria)

            # Step KPIs
            if kpis:
                _add_header(doc, "Step KPIs:")
                if isinstance(kpis, list):
                    for k in kpis:
                        _add_bullet(doc, k)
                else:
                    _add_bullet(doc, kpis)

            # Escalation Procedure
            if escalation:
                _add_header(doc, "Escalation Procedure:")
                _add_bullet(doc, escalation)

            # Subprocess render
            subprocess_json = step.get("subprocess")
            if isinstance(subprocess_json, dict):
                _add_subprocess_section(doc, name, subprocess_json)

            doc.add_paragraph().paragraph_format.space_after = Pt(0)
    except Exception:
        logger.exception(f"Failed to render subprocess steps for {current_step_name}")           

def _add_step_diagram_if_available(
    doc: docx.Document,
    step_name: str,
    subprocess_json: dict,
) -> None:
    """
    Generate and embed a subprocess diagram for the given step, if possible.
    Uses the micro-BPMN generator by default.
    """
    try:
        diagram_path = generate_step_diagram_for_step(step_name, subprocess_json)
        if not diagram_path:
            return
        if not os.path.exists(diagram_path):
            return

        doc.add_picture(diagram_path, width=Inches(5.5))
        doc.add_paragraph()  # spacer
    except Exception:
        traceback.print_exc()

def _add_subprocess_section(doc: docx.Document, step_name: str, subprocess_json: dict) -> None:
    """
    Renders subprocess flows using the new explicit subprocess schema:
    - substep_name
    - description
    - responsible_party
    - inputs, outputs
    - estimated_duration
    - dependencies
    - success_criteria
    - purpose, scope, process_owner
    - triggers, end_conditions
    - step_risks_and_controls: [{risk, control}]
    - governance_requirements: [str]
    - change_management: [{change_request_process, versioning_rules}]
    - continuous_improvement: [{review_frequency, improvement_inputs}]
    """
    logger.info(f"Rendering subprocess for step: {step_name}")

    try:
        doc.add_heading(f"Required Sub Process(es) for the Step \"{step_name}\"", level=3)
        doc.add_paragraph(f"The following details the subprocess flows for the step \"{step_name}\".")

        # Optional micro-diagram
        _add_step_diagram_if_available(doc, step_name, subprocess_json)

        # Optional high-level description
        if "description" in subprocess_json:
            doc.add_paragraph(str(subprocess_json["description"]))

        # Identify substep list
        substeps = None
        for key in ["subprocess_flow", "subprocess_steps", "steps", "flow", "phases", "substeps", "activities"]:
            if key in subprocess_json and isinstance(subprocess_json[key], list):
                substeps = subprocess_json[key]
                break

        # Fallback: any list of dicts
        if substeps is None:
            for k, v in subprocess_json.items():
                if isinstance(v, list) and all(isinstance(x, dict) for x in v):
                    substeps = v
                    break

        if not substeps:
            doc.add_paragraph("No structured subprocess steps found. Rendering raw subprocess data:")
            _render_generic_value(doc, subprocess_json, level=1)
            doc.add_paragraph()
            return

        # Render each substep
        for idx, s in enumerate(substeps, start=1):
            if not isinstance(s, dict):
                continue

            # Substep name
            sname = (
                s.get("substep_name")
                or s.get("step_name")
                or s.get("name")
                or s.get("title")
                or f"Sub-step {idx}"
            )

            doc.add_heading(f"{step_name} – {sname}", level=4)

            # Ordered fields for consistent rendering
            ordered_fields = [
                ("description", "Description"),
                ("responsible_party", "Responsible Party"),
                ("inputs", "Inputs"),
                ("outputs", "Outputs"),
                ("estimated_duration", "Estimated Duration"),
                ("dependencies", "Dependencies"),
                ("success_criteria", "Success Criteria"),
                ("purpose", "Purpose"),
                ("scope", "Scope"),
                ("process_owner", "Process Owner"),
                ("triggers", "Triggers"),
                ("end_conditions", "End Conditions"),
            ]

            # Render simple fields using helpers
            for field, label in ordered_fields:
                if field not in s:
                    continue

                value = s[field]

                # Header line (10pt before, 0pt after)
                _add_header(doc, f"{label}:")

                # Bullet(s)
                if isinstance(value, list):
                    for item in value:
                        _add_bullet(doc, item)
                else:
                    _add_bullet(doc, value)

            # --- Complex structured fields ---

            # step_risks_and_controls
            if "step_risks_and_controls" in s:
                _add_header(doc, "Step Risks and Controls:")

                for rc in s["step_risks_and_controls"]:
                    if isinstance(rc, dict):
                        _add_bullet(doc, f"Risk: {rc.get('risk', '')}")
                        _add_bullet(doc, f"Control: {rc.get('control', '')}")


            # governance_requirements
            if "governance_requirements" in s:
                _add_header(doc, "Governance Requirements:")
                for item in s["governance_requirements"]:
                    _add_bullet(doc, item)

            # change_management
            if "change_management" in s:
                _add_header(doc, "Change Management:")
                for cm in s["change_management"]:
                    if isinstance(cm, dict):
                        _add_bullet(doc, f"Change Request Process: {cm.get('change_request_process', '')}")
                        _add_bullet(doc, f"Versioning Rules: {cm.get('versioning_rules', '')}")

            # continuous_improvement
            if "continuous_improvement" in s:
                _add_header(doc, "Continuous Improvement:")
                for ci in s["continuous_improvement"]:
                    if isinstance(ci, dict):
                        _add_bullet(doc, f"Review Frequency: {ci.get('review_frequency', '')}")

                        inputs = ci.get("improvement_inputs", [])
                        if inputs:
                            _add_header(doc, "Improvement Inputs:")
                            for item in inputs:
                                _add_bullet(doc, item)

            # Schema drift protection
            known = {
                f for f, _ in ordered_fields
            } | {
                "substep_name",
                "step_risks_and_controls",
                "governance_requirements",
                "change_management",
                "continuous_improvement",
            }

            extra = {k: v for k, v in s.items() if k not in known}
            if extra:
                doc.add_paragraph().add_run("Additional Details:").bold = True
                _render_generic_value(doc, extra, level=1)

            doc.add_paragraph()

    except Exception:
        logger.exception(f"Failed to render subprocess for {step_name}")

def _render_generic_value(doc: docx.Document, value, level: int = 0) -> None:
    """
    Generic recursive renderer for unknown structures.
    This ensures ANY business-process JSON can be turned into readable content.
    Fully defensive: type-checks at every step.
    """
    try:
        indent_style = "List Bullet" if level > 0 else "Normal"

        if isinstance(value, dict):
            for k, v in value.items():
                p = doc.add_paragraph(style=indent_style)
                r = p.add_run(f"{str(k).replace('_', ' ').title()}: ")
                r.bold = True
                if isinstance(v, (dict, list)):
                    _render_generic_value(doc, v, level + 1)
                else:
                    p.add_run(str(v))

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    _render_generic_value(doc, item, level + 1)
                else:
                    doc.add_paragraph(str(item), style=indent_style)

        else:
            doc.add_paragraph(str(value), style=indent_style)
    except Exception:
        traceback.print_exc()

def _add_tools_section_from_summary(doc: docx.Document, tools_summary) -> None:
    """4.0 Tools section: 'tools_summary' list of {category, tools}."""
    try:
        if not isinstance(tools_summary, list) or not tools_summary:
            return

        doc.add_heading("4.0 Supporting Systems and Tools", level=1)
        doc.add_paragraph("The following tools and platforms support this process:")

        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Category"
        hdr_cells[1].text = "Tools"

        for entry in tools_summary:
            category = entry.get("category", "")
            tools = entry.get("tools", [])

            row_cells = table.add_row().cells
            row_cells[0].text = str(category)

            if isinstance(tools, list):
                row_cells[1].text = ", ".join(str(x) for x in tools)
            else:
                row_cells[1].text = str(tools)

        doc.add_paragraph()

    except Exception:
        traceback.print_exc()
