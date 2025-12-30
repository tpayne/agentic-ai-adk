# process_agents/doc_generation_agent.py
from google.adk.agents import LlmAgent
import docx
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from step_diagram_agent import ( 
    generate_step_diagram_for_step, 
)

import os
import json

from datetime import datetime
import traceback

import logging

logger = logging.getLogger("ProcessArchitect.DocGen")

# -----------------------------------
# Subprocess support
# -----------------------------------

def _load_subprocesses() -> dict:
    """
    Loads all subprocess JSON files from output/subprocesses/.
    Returns a dict: { step_name: subprocess_json }
    """
    logger.info("Loading subprocess JSON files...")
    subprocess_dir = "output/subprocesses"
    subprocesses = {}

    if not os.path.isdir(subprocess_dir):
        return subprocesses

    for filename in os.listdir(subprocess_dir):
        if not filename.endswith(".json"):
            continue

        path = os.path.join(subprocess_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            parent = data.get("parent_step_name") or data.get("step_name")
            if parent:
                subprocesses[parent] = data

        except Exception:
            logger.exception(f"Failed to load subprocess file: {path}")

    return subprocesses

# -----------------------------------
# Helpers: Document building blocks
# -----------------------------------

def _add_table_of_contents(doc: docx.Document) -> None:
    """
    Insert a Word Table of Contents field (updates inside Word).
    The user must right-click and 'Update Field' after opening.
    """
    try:
        paragraph = doc.add_paragraph()
        run = paragraph.add_run()

        fld_simple = OxmlElement('w:fldSimple')
        fld_simple.set(
            qn('w:instr'),
            'TOC \\o "1-3" \\h \\z \\u'
        )
        run._r.append(fld_simple)

        inner_run = OxmlElement('w:r')
        t = OxmlElement('w:t')
        t.text = "Right-click and select 'Update Field' to generate the Table of Contents."
        inner_run.append(t)
        fld_simple.append(inner_run)
    except Exception:
        traceback.print_exc()


def _add_version_history_table(doc: docx.Document, version: str, author: str) -> None:
    """Add a basic version history table derived from JSON or defaults."""
    try:
        doc.add_heading("Document Control", level=1)

        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Version"
        hdr_cells[1].text = "Date"
        hdr_cells[2].text = "Author"
        hdr_cells[3].text = "Description"

        row_cells = table.add_row().cells
        row_cells[0].text = str(version)
        row_cells[1].text = datetime.now().strftime("%Y-%m-%d")
        row_cells[2].text = str(author)
        row_cells[3].text = "Initial generated process specification"

        doc.add_paragraph()  # spacer
    except Exception:
        traceback.print_exc()

def _add_process_step_summary(doc, step: dict) -> None:
    """Render a clean, human-readable summary of a process step."""
    name = step.get("step_name") or step.get("name")
    if name:
        doc.add_heading(name, level=2)

    desc = step.get("description")
    if desc:
        doc.add_paragraph(desc)

    duration = step.get("estimated_duration")
    if duration:
        doc.add_paragraph(f"Estimated Duration: {duration}")

    parties = step.get("responsible_party")
    if parties:
        doc.add_paragraph(f"Responsible Parties: {parties}")

    activities = step.get("activities")
    if activities:
        doc.add_paragraph("Key Activities:")
        for a in activities:
            doc.add_paragraph(f"- {a}", style="List Bullet")

    criteria = step.get("success_criteria")
    if criteria:
        doc.add_paragraph("Success Criteria:")
        for c in criteria:
            doc.add_paragraph(f"- {c}", style="List Bullet")

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


# -----------------------------------
# Schema-aware renderers (for normalized JSON)
# -----------------------------------

def _add_overview_section(doc: docx.Document, data: dict) -> None:
    """
    1.0 Process Overview.

    Renders:
    - introduction or description
    - assumptions
    - constraints
    - high-level metadata (purpose, scope, etc.)

    It intentionally does NOT render full step details; those live in 3.0.
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

        # --- Assumptions ---
        assumptions = data.get("assumptions")
        if "assumptions" in process_data and process_data["assumptions"]:
            if isinstance(assumptions, list) and assumptions:
               doc.add_heading("1.1 Assumptions", level=2)
               for item in assumptions:
                   doc.add_paragraph(item, style='List Bullet')

        # --- Constraints ---
        constraints = data.get("constraints")
        if "constraints" in process_data and process_data["constraints"]:
            if isinstance(constraints, list) and constraints:
               doc.add_heading("1.2 Constraints", level=2)
               for item in constraints:
                   doc.add_paragraph(item, style='List Bullet')

        # --- High-level metadata ---
        high_level_keys = [
            "purpose",
            "scope",
            "out_of_scope",
            "industry_sector",
            "business_unit",
            "owner",
        ]

        for key in high_level_keys:
            if key in data:
                p = doc.add_paragraph()
                r = p.add_run(f"{key.replace('_', ' ').title()}: ")
                r.bold = True
                p.add_run(str(data.get(key)))

        # NOTE: No step summaries here. 3.0 already covers process_steps.

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
    try:
        if not isinstance(steps, list) or not steps:
            return

        doc.add_heading("3.0 Process Workflow", level=1)
        doc.add_paragraph(
            f"The following is a list of key steps in the process workflow."
        )
        for s_idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue

            step_no = step.get("step_number") or step.get("step_id") or s_idx
            name = step.get("step_name", f"Step {step_no}")
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

            if description:
                doc.add_paragraph(str(description))

            if responsible:
                p = doc.add_paragraph()
                r = p.add_run("Responsible Parties: ")
                r.bold = True
                if isinstance(responsible, list):
                    p.add_run(", ".join(str(x) for x in responsible))
                else:
                    p.add_run(str(responsible))

            if inputs:
                p = doc.add_paragraph()
                r = p.add_run("Inputs: ")
                r.bold = True
                if isinstance(inputs, list):
                    for i in inputs:
                        doc.add_paragraph(str(i), style="List Bullet")
                else:
                    doc.add_paragraph(str(inputs), style="List Bullet")

            if outputs:
                p = doc.add_paragraph()
                r = p.add_run("Outputs: ")
                r.bold = True
                if isinstance(outputs, list):
                    for o in outputs:
                        doc.add_paragraph(str(o), style="List Bullet")
                else:
                    doc.add_paragraph(str(outputs), style="List Bullet")

            if activities and isinstance(activities, list):
                p = doc.add_paragraph()
                r = p.add_run("Key Activities: ")
                r.bold = True
                for a in activities:
                    doc.add_paragraph(str(a), style="List Bullet")

            if sub_steps and isinstance(sub_steps, list):
                doc.add_paragraph()
                p = doc.add_paragraph()
                r = p.add_run("Sub-Steps:")
                r.bold = True

                for idx_sub, sub in enumerate(sub_steps, start=1):
                    if not isinstance(sub, dict):
                        continue
                    ss_name = sub.get("sub_step_name", f"Sub-step {idx_sub}")
                    ss_desc = sub.get("sub_step_description", "")
                    ss_acts = sub.get("activities", [])

                    doc.add_heading(f"3.{s_idx}.{idx_sub} {ss_name}", level=3)
                    if ss_desc:
                        doc.add_paragraph(str(ss_desc))
                    if isinstance(ss_acts, list) and ss_acts:
                        for act in ss_acts:
                            doc.add_paragraph(str(act), style="List Bullet")

            if success_criteria:
                p = doc.add_paragraph()
                r = p.add_run("Success Criteria:")
                r.bold = True

                if isinstance(success_criteria, list):
                    for crit in success_criteria:
                        # Proper bullet formatting
                        doc.add_paragraph(str(crit), style="List Bullet")
                else:
                    doc.add_paragraph(str(success_criteria), style="List Bullet")

            if kpis:
                p = doc.add_paragraph()
                r = p.add_run("Step KPIs: ")
                r.bold = True
                if isinstance(kpis, list):
                    for k in kpis:
                        doc.add_paragraph(str(k), style="List Bullet")
                else:
                    doc.add_paragraph(str(kpis), style="List Bullet")

            if escalation:
                p = doc.add_paragraph()
                r = p.add_run("Escalation Procedure: ")
                r.bold = True
                doc.add_paragraph(str(escalation), style="Normal")

            # --- Subprocess render (if attached) ---
            subprocess_json = step.get("subprocess")
            if isinstance(subprocess_json, dict):
                _add_subprocess_section(doc, name, subprocess_json)

            doc.add_paragraph()
    except Exception:
        traceback.print_exc()


def _add_subprocess_section(doc: docx.Document, step_name: str, subprocess_json: dict) -> None:
    """
    Fully hardened subprocess renderer.
    Accepts ANY reasonable subprocess schema and renders it safely.

    Supports:
    - subprocess_flow
    - subprocess_steps
    - steps
    - flow
    - phases
    - arbitrary nested structures

    Also supports substep_name, step_name, name, title, etc.
    """
    logger.info(f"Rendering subprocess for step: {step_name}")
    try:
        doc.add_heading(f"Required Sub Process(es) for the Step \"{step_name}\"", level=3)
        doc.add_paragraph(f"The following details the subprocess flows for the step \"{step_name}\".")

        # 🔥 NEW: generate and embed a subprocess diagram (per-step micro-BPMN)
        _add_step_diagram_if_available(doc, step_name, subprocess_json)

        # Optional high-level description
        desc = subprocess_json.get("description")
        if desc:
            doc.add_paragraph(str(desc))

        # --- Identify substep container keys (max compatibility) ---
        candidate_keys = [
            "subprocess_steps",
            "subprocess_flow",
            "steps",
            "flow",
            "phases",
            "substeps",
            "activities",   # fallback if LLM outputs activities as substeps
        ]

        substeps = None
        for key in candidate_keys:
            if key in subprocess_json and isinstance(subprocess_json[key], list):
                substeps = subprocess_json[key]
                break

        # If still nothing, try to detect any list of dicts
        if substeps is None:
            for k, v in subprocess_json.items():
                if isinstance(v, list) and all(isinstance(x, dict) for x in v):
                    substeps = v
                    break

        # If STILL nothing, render the whole subprocess JSON generically
        if not substeps:
            doc.add_paragraph("No structured subprocess steps found. Rendering raw subprocess data:")
            _render_generic_value(doc, subprocess_json, level=1)
            doc.add_paragraph()
            return

        # --- Render each substep ---
        for idx, s in enumerate(substeps, start=1):
            if not isinstance(s, dict):
                continue

            # Identify substep name field
            name_fields = [
                "substep_name",
                "step_name",
                "name",
                "title",
                "label",
            ]
            sname = None
            for nf in name_fields:
                if nf in s:
                    sname = s[nf]
                    break
            if not sname:
                sname = f"Sub-step {idx}"

            doc.add_heading(f"{step_name} – {sname}", level=4)

            # Known fields
            known_fields = {
                "description": "Description",
                "responsible_party": "Responsible Parties",
                "inputs": "Inputs",
                "outputs": "Outputs",
                "dependencies": "Dependencies",
                "estimated_duration": "Estimated Duration",
                "success_criteria": "Success Criteria",
            }

            # Render known fields first
            for field, label in known_fields.items():
                if field not in s:
                    continue

                value = s[field]
                p = doc.add_paragraph()
                r = p.add_run(f"{label}: ")
                r.bold = True

                if isinstance(value, list):
                    for item in value:
                        doc.add_paragraph(str(item), style="List Bullet")
                else:
                    p.add_run(str(value))

            # Render any unknown fields (schema drift protection)
            extra = {
                k: v for k, v in s.items()
                if k not in known_fields and k not in name_fields
            }
            if extra:
                doc.add_paragraph().add_run("Additional Details:").bold = True
                _render_generic_value(doc, extra, level=1)

            doc.add_paragraph()

    except Exception:
        logger.exception(f"Failed to render subprocess for {step_name}")


def _add_tools_section_from_summary(doc: docx.Document, tools_summary: dict) -> None:
    """4.0 Tools section: 'tools_summary' dict."""
    try:
        if not isinstance(tools_summary, dict) or not tools_summary:
            return

        doc.add_heading("4.0 Supporting Systems and Tools", level=1)
        doc.add_paragraph("The following tools and platforms support this process:")

        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Category"
        hdr_cells[1].text = "Tools"

        for category, tools in tools_summary.items():
            row_cells = table.add_row().cells
            row_cells[0].text = str(category).replace("_", " ").title()

            if isinstance(tools, list):
                row_cells[1].text = ", ".join(str(x) for x in tools)
            else:
                row_cells[1].text = str(tools)

        doc.add_paragraph()
    except Exception:
        traceback.print_exc()


def _add_metrics_section(doc: docx.Document, metrics) -> None:
    """
    5.0 Metrics & KPIs section.

    Normalized expectation:
    - metrics: list of dicts with keys like:
      metric_name, description, measurement_frequency, target
    or
    - metrics: list of strings.
    """
    try:
        if not isinstance(metrics, list) or not metrics:
            return

        doc.add_heading("5.0 Metrics and Key Performance Indicators (KPIs)", level=1)

        doc.add_paragraph(
            f"The following is a list of key metrics associated with this process. "
            f"These metrics help monitor performance and ensure alignment with business objectives."
        )

        if metrics and all(isinstance(m, str) for m in metrics):
            for m in metrics:
                doc.add_paragraph(m, style="List Bullet")
            return

        for idx, m in enumerate(metrics, start=1):
            if isinstance(m, str):
                doc.add_paragraph(m, style="List Bullet")
                continue
            if not isinstance(m, dict):
                continue

            name = ( m.get("name") or m.get("metric_name") or f"Metric {idx}" )
            description = m.get("description", "")
            measurement = (
                m.get("measurement")
                or m.get("measurement_frequency")
                or ""
            )
            target = m.get("target", "")
            sub_metrics = m.get("sub_metrics", [])

            doc.add_heading(str(name), level=2)
            if description:
                doc.add_paragraph(str(description))
            if measurement:
                p = doc.add_paragraph()
                r = p.add_run("Measurement / Frequency: ")
                r.bold = True
                p.add_run(str(measurement))
            if target:
                p = doc.add_paragraph()
                r = p.add_run("Target: ")
                r.bold = True
                p.add_run(str(target))

            if isinstance(sub_metrics, list) and sub_metrics:
                doc.add_paragraph().add_run("Sub-metrics:").bold = True
                for sm in sub_metrics:
                    if isinstance(sm, str):
                        doc.add_paragraph(sm, style="List Bullet")
                    elif isinstance(sm, dict):
                        line = sm.get("metric_name", "Sub-metric")
                        if "description" in sm:
                            line = f"{line} – {sm['description']}"
                        doc.add_paragraph(line, style="List Bullet")
    except Exception:
        traceback.print_exc()


def _add_simulation_report(doc: docx.Document, simulation_results: dict) -> None:
    """
    9.0 Process Performance Report.
    Renders simulation metrics with appropriate time units.
    """
    try:
        if not isinstance(simulation_results, dict) or not simulation_results:
            return

        time_unit = str(simulation_results.get("time_unit", "units"))

        doc.add_heading("9.0 Process Performance Report", level=1)
        
        doc.add_paragraph(
            f"The following metrics are based on a Monte Carlo discrete-event simulation "
            f"running 2,000 iterations. All time-based values are reported in {time_unit}."
        )

        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "Operational Metric"
        hdr[1].text = "Simulated Value"

        metrics_to_show = [
            ("avg_cycle_time", "Average Cycle Time"),
            ("cycle_time_variance", "Cycle Time Variance"),
            ("resource_contention_risk", "Contention Risk Profile")
        ]

        for key, label in metrics_to_show:
            if key in simulation_results:
                row = table.add_row().cells
                row[0].text = label
                val = simulation_results[key]
                
                if "cycle_time" in key:
                    try:
                        row[1].text = f"{float(val):.2f} {time_unit}"
                    except:
                        row[1].text = f"{val} {time_unit}"
                else:
                    row[1].text = str(val)

        doc.add_paragraph()

        if "bottlenecks" in simulation_results:
            doc.add_heading("Identified Bottlenecks", level=2)
            for b in simulation_results["bottlenecks"]:
                doc.add_paragraph(str(b), style="List Bullet")

        if "per_step_avg" in simulation_results:
            doc.add_heading("Detailed Step Performance", level=2)
            table2 = doc.add_table(rows=1, cols=2)
            table2.style = "Table Grid"
            hdr2 = table2.rows[0].cells
            hdr2[0].text = "Process Step"
            hdr2[1].text = f"Avg. Duration ({time_unit})"

            for step, avg in simulation_results["per_step_avg"].items():
                row = table2.add_row().cells
                row[0].text = str(step)
                try:
                    row[1].text = f"{float(avg):.2f}"
                except:
                    row[1].text = str(avg)

        doc.add_paragraph()

        if "recommendations" in simulation_results and isinstance(simulation_results["recommendations"], list):
            doc.add_heading("Optimization Recommendations", level=2)
            for rec in simulation_results["recommendations"]:
                if not isinstance(rec, dict):
                    continue
                step_name = rec.get("step_name", "Step")
                instruction = rec.get("instruction", "")
                line = f"{step_name}: {instruction}"
                doc.add_paragraph(line, style="List Bullet")

    except Exception as e:
        logger.error(f"Error rendering simulation report: {e}")
        traceback.print_exc()


def _add_reporting_and_analytics(doc: docx.Document, ra) -> None:
    try:
        if ra is None:
            return

        doc.add_heading("6.0 Reporting and Analytics", level=1)
        doc.add_paragraph(
            f"The following are key reporting and analytics associated with this process."
        )

        def flatten_value(v):
            if isinstance(v, dict):
                parts = []
                for k2, v2 in v.items():
                    parts.append(f"{k2.replace('_',' ').title()}: {flatten_value(v2)}")
                return "; ".join(parts)
            elif isinstance(v, list):
                return ", ".join(flatten_value(x) for x in v)
            else:
                return str(v)

        if isinstance(ra, dict):
            table = doc.add_table(rows=1, cols=2)
            table.style = "Table Grid"
            hdr = table.rows[0].cells
            hdr[0].text = "Metric / Key"
            hdr[1].text = "Description / Value"

            for key, value in ra.items():
                row = table.add_row().cells
                row[0].text = key.replace("_", " ").title()
                row[1].text = flatten_value(value)

            doc.add_paragraph()
            return

        if isinstance(ra, list) and all(isinstance(x, (str, int, float)) for x in ra):
            for item in ra:
                doc.add_paragraph(str(item), style="List Bullet")
            doc.add_paragraph()
            return

        if isinstance(ra, list) and all(isinstance(x, dict) for x in ra):
            all_keys = set()
            for item in ra:
                all_keys.update(item.keys())
            all_keys = sorted(all_keys)

            table = doc.add_table(rows=1, cols=len(all_keys))
            table.style = "Table Grid"

            hdr = table.rows[0].cells
            for idx, key in enumerate(all_keys):
                hdr[idx].text = key.replace("_", " ").title()

            for item in ra:
                row = table.add_row().cells
                for idx, key in enumerate(all_keys):
                    val = item.get(key, "")
                    row[idx].text = flatten_value(val)

            doc.add_paragraph()
            return

        doc.add_paragraph(
            "The reporting and analytics structure contains mixed or nested data. "
            "The following section renders it in a readable hierarchical format."
        )

        def render_recursive(value, level=0):
            indent_style = "List Bullet" if level > 0 else "Normal"

            if isinstance(value, dict):
                for k, v in value.items():
                    p = doc.add_paragraph(style=indent_style)
                    r = p.add_run(f"{k.replace('_',' ').title()}: ")
                    r.bold = True
                    if isinstance(v, (dict, list)):
                        render_recursive(v, level + 1)
                    else:
                        p.add_run(str(v))

            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, (dict, list)):
                        render_recursive(item, level + 1)
                    else:
                        doc.add_paragraph(str(item), style=indent_style)

            else:
                doc.add_paragraph(str(value), style=indent_style)

        render_recursive(ra)
        doc.add_paragraph()

    except Exception:
        traceback.print_exc()


def _add_system_requirements(doc: docx.Document, system_requirements) -> None:
    try:
        if not isinstance(system_requirements, list) or not system_requirements:
            return

        doc.add_heading("7.0 System Requirements", level=1)
        doc.add_paragraph(
            f"The following system requirements are essential for the successful implementation of this process."
        )

        if all(isinstance(item, dict) for item in system_requirements):
            all_keys = set()
            for item in system_requirements:
                all_keys.update(item.keys())
            all_keys = sorted(all_keys)

            table = doc.add_table(rows=1, cols=len(all_keys))
            table.style = "Table Grid"

            hdr = table.rows[0].cells
            for idx, key in enumerate(all_keys):
                hdr[idx].text = key.replace("_", " ").title()

            for item in system_requirements:
                row = table.add_row().cells
                for idx, key in enumerate(all_keys):
                    val = item.get(key, "")
                    if isinstance(val, dict):
                        row[idx].text = "; ".join(
                            f"{k}: {v}" for k, v in val.items()
                        )
                    elif isinstance(val, list):
                        row[idx].text = ", ".join(str(x) for x in val)
                    else:
                        row[idx].text = str(val)

            doc.add_paragraph()
            return

        if all(isinstance(item, (str, int, float)) for item in system_requirements):
            for item in system_requirements:
                doc.add_paragraph(str(item), style="List Bullet")
            doc.add_paragraph()
            return

        doc.add_paragraph(
            "The system requirements contain mixed or nested data. "
            "The following section renders them in a readable hierarchical format."
        )

        def render_recursive(value, level=0):
            indent_style = "List Bullet" if level > 0 else "Normal"

            if isinstance(value, dict):
                for k, v in value.items():
                    p = doc.add_paragraph(style=indent_style)
                    r = p.add_run(f"{k.replace('_',' ').title()}: ")
                    r.bold = True
                    if isinstance(v, (dict, list)):
                        render_recursive(v, level + 1)
                    else:
                        p.add_run(str(v))

            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, (dict, list)):
                        render_recursive(item, level + 1)
                    else:
                        doc.add_paragraph(str(item), style=indent_style)

            else:
                doc.add_paragraph(str(value), style=indent_style)

        render_recursive(system_requirements)
        doc.add_paragraph()

    except Exception:
        traceback.print_exc()


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


def _add_flowchart_section(doc: docx.Document, process_name: str) -> None:
    """8.0 Flow diagram section if a PNG already exists. Defensive."""
    try:
        diag_file = f"output/{process_name.lower().replace(' ', '_')}_flow.png"
        if not os.path.exists(diag_file):
            return

        doc.add_heading("8.0 Process Flow Diagram", level=1)
        doc.add_paragraph(
            "The following diagram provides a high-level visualization of the process flow as defined in the normalized JSON source."
        )
        doc.add_picture(diag_file, width=Inches(5.5))
        doc.add_paragraph()
    except Exception:
        traceback.print_exc()


def _add_appendix_from_json(doc: docx.Document, appendix: dict) -> None:
    """Appendix A: structured appendix content from JSON. Defensive."""
    try:
        if not isinstance(appendix, dict) or not appendix:
            return

        doc.add_heading("Appendix A: Reference Documents", level=1)
        doc.add_paragraph(
            f"The following appendix contains reference materials related to the process."
        )
        for key, val in appendix.items():
            section_title = str(key).replace("_", " ").title()
            doc.add_heading(section_title, level=2)

            if isinstance(val, dict):
                summary = val.get("summary")
                if summary:
                    p = doc.add_paragraph()
                    r = p.add_run("Summary: ")
                    r.bold = True
                    doc.add_paragraph(str(summary), style="Normal")

                last_reviewed = val.get("last_reviewed")
                if last_reviewed:
                    p = doc.add_paragraph()
                    r = p.add_run("Last Reviewed: ")
                    r.bold = True
                    p.add_run(str(last_reviewed))

                review_frequency = val.get("review_frequency")
                if review_frequency:
                    p = doc.add_paragraph()
                    r = p.add_run("Review Frequency: ")
                    r.bold = True
                    p.add_run(str(review_frequency))

                extra = {
                    k: v for k, v in val.items()
                    if k not in {"summary", "last_reviewed", "review_frequency"}
                }
                if extra:
                    _render_generic_value(doc, extra, level=1)
            else:
                _render_generic_value(doc, val, level=1)
    except Exception:
        traceback.print_exc()


def _add_additional_data_section(doc: docx.Document, data: dict, consumed_keys: set) -> None:
    """
    Appendix B for any remaining JSON keys not explicitly handled.
    Ensures the document always reflects the full JSON, even for unknown schemas.
    Defensive.
    """
    try:
        if not isinstance(data, dict):
            return

        remaining = {k: v for k, v in data.items() if k not in consumed_keys}
        if not remaining:
            return

        doc.add_heading("Appendix B: Additional Source Data", level=1)
        doc.add_paragraph(
            "This appendix contains additional structured data from the normalized source JSON that is not covered in the main sections."
        )
        _render_generic_value(doc, remaining, level=0)
    except Exception:
        traceback.print_exc()


def _add_glossary(doc: docx.Document) -> None:
    """Appendix C: Generic glossary for common process terminology."""
    try:
        doc.add_heading("Appendix C: Glossary", level=1)
        doc.add_paragraph(
            "This glossary contains definitions of common terms used in the process documentation."
        )
        terms = {
            "Business Process": "A set of related activities or tasks performed to achieve a specific organizational goal.",
            "KPI": "Key Performance Indicator used to measure the success or health of a process.",
            "Stakeholder": "Any individual or group with an interest in the outcomes of the process.",
            "Continuous Improvement": "Ongoing effort to improve products, services or processes.",
        }

        # Render glossary as a table instead of a list
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Term"
        hdr_cells[1].text = "Definition"

        for term, definition in terms.items():
            row_cells = table.add_row().cells
            row_cells[0].text = term
            row_cells[1].text = definition
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------
# Main: Structured process document generation logic
# ---------------------------------------------------

def create_standard_doc_from_file(process_name: str) -> str:
    """
    Generate a structured, professional process document from process_data.json.

    EXPECTATION:
    - process_data.json contains normalized, document-ready JSON as described
      at the top of this file.
    - This function is schema-aware for that normalized format and will:
      * Build a professional title page.
      * Add document control + TOC.
      * Render overview, stakeholders, workflow, tools, metrics, reporting,
        system requirements, flow diagram, and appendices.
    """
    print(f"Creating document for process: {process_name}...")
    logger.info(f"Creating document for process: {process_name}...")
    try:
        logger.info(f"Loading process data from output/process_data.json...")
        with open("output/process_data.json", 'r', encoding="utf-8") as f:
            try:
                raw_data = json.load(f)
            except Exception:
                traceback.print_exc()
                return "ERROR: Failed to parse process_data.json"

        if isinstance(raw_data, dict) and "process_design" in raw_data and isinstance(raw_data["process_design"], dict):
            data = raw_data["process_design"]
        elif isinstance(raw_data, dict):
            data = raw_data
        else:
            data = {"root": raw_data}

        # Attach subprocesses to steps (if any)
        subprocesses = _load_subprocesses()
        for step in data.get("process_steps", []):
            if isinstance(step, dict):
                name = step.get("step_name")
                if name in subprocesses:
                    step["subprocess"] = subprocesses[name]

        name = str(data.get("process_name", process_name))
        description = data.get("description") or data.get("process_description") or data.get("introduction")
        version = str(data.get("version", "1.0"))
        sector = data.get("industry_sector", data.get("business_unit", data.get("sector", ""))) or "N/A"

        stakeholders = data.get("stakeholders")
        process_steps = data.get("process_steps")
        tools_summary = data.get("tools_summary")
        metrics = data.get("metrics") or data.get("success_metrics")
        reporting_and_analytics = data.get("reporting_and_analytics")
        system_requirements = data.get("system_requirements")
        appendix = data.get("appendix") if isinstance(data.get("appendix"), dict) else None

        consumed_keys = { 
            "process_name", 
            "description", 
            "process_description", 
            "introduction", 
            "version", 
            "industry_sector", 
            "business_unit", 
            "stakeholders", 
            "process_steps", 
            "tools_summary", 
            "metrics", 
            "success_metrics", 
            "reporting_and_analytics", 
            "system_requirements", 
            "appendix",
        }

        doc = docx.Document()
        try:
            doc.core_properties.title = name
            doc.core_properties.subject = "Business Process Specification"
            doc.core_properties.category = sector
            doc.core_properties.author = "Process Architect"
        except Exception:
            traceback.print_exc()

        # TITLE PAGE
        try:
            title = doc.add_heading(name, 0)
            if title.runs:
                title.runs[0].font.size = Pt(24)
        except Exception:
            traceback.print_exc()

        if description:
            doc.add_paragraph(str(description))

        p = doc.add_paragraph()
        p.add_run("Industry / Domain: ").bold = True
        p.add_run(str(sector))

        p = doc.add_paragraph()
        p.add_run("Version: ").bold = True
        p.add_run(str(version))

        p = doc.add_paragraph()
        p.add_run("Generated On: ").bold = True
        p.add_run(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        doc.add_page_break()

        # DOCUMENT CONTROL + TOC
        _add_version_history_table(doc, version=version, author="Process Architect")

        doc.add_page_break()
        doc.add_heading("Table of Contents", level=1)
        _add_table_of_contents(doc)
        doc.add_page_break()

        # 1.0 Overview
        _add_overview_section(doc, data)
        doc.add_page_break()

        # 2.0 Stakeholders
        _add_stakeholders_section(doc, stakeholders)
        doc.add_page_break()

        # 3.0 Process Steps
        if process_steps:
            _add_process_steps_section(doc, process_steps)
            doc.add_page_break()

        # 4.0 Tools / Systems (from tools_summary)
        if tools_summary:
            _add_tools_section_from_summary(doc, tools_summary)

        # 5.0 Metrics
        if isinstance(metrics, list) and metrics:
            _add_metrics_section(doc, metrics)
            doc.add_page_break()

        # 6.0 Reporting & Analytics
        if reporting_and_analytics:
            _add_reporting_and_analytics(doc, reporting_and_analytics)
            doc.add_page_break()

        # 7.0 System Requirements
        if system_requirements:
            _add_system_requirements(doc, system_requirements)
            doc.add_page_break()

        # 8.0 Flow Diagram
        _add_flowchart_section(doc, name)
        doc.add_page_break()

        # Load simulation results if present
        simulation_results = None
        try:
            sim_path = "output/simulation_results.json"
            if os.path.exists(sim_path):
                with open(sim_path, "r", encoding="utf-8") as sf:
                    simulation_results = json.load(sf)
        except Exception:
            traceback.print_exc()
            simulation_results = None

        # 9.0 Process Performance Report (if we have metrics)
        if simulation_results:
            _add_simulation_report(doc, simulation_results)
            doc.add_page_break()

        # Appendix A: Structured appendix from JSON
        if appendix:
            _add_appendix_from_json(doc, appendix)
            consumed_keys.add("appendix")

        # Appendix B: Remaining JSON
        doc.add_page_break()
        _add_additional_data_section(doc, data, consumed_keys)

        # Appendix C: Glossary
        doc.add_page_break()
        _add_glossary(doc)

        try:
            out_path = f"output/{name.replace(' ', '_')}.docx"
            doc.save(out_path)
            return f"SUCCESS: Professional document saved at {out_path}"
        except Exception:
            traceback.print_exc()
            return "ERROR: Failed to save Word document"

    except Exception as e:
        traceback.print_exc()
        return f"ERROR: {str(e)}"


# --------------------------
# Agent definition
# --------------------------

doc_generation_agent = LlmAgent(
    name="Document_Generation_Agent",
    model="gemini-2.0-flash-001",
    description="Generates a professional Word document from normalized JSON.",
    instruction=(
        "You are a Documentation Automation Specialist.\n\n"
        "CONTEXT:\n"
        "- The normalized process JSON has already been saved to output/process_data.json.\n"
        "- A process flow diagram PNG may already exist in the output folder, generated "
        "  by another agent.\n\n"
        "YOUR TASK:\n"
        "- Call create_standard_doc_from_file exactly once using the process_name.\n"
        "- The function will:\n"
        "    * Load output/process_data.json\n"
        "    * Build a professional, structured Word document\n"
        "    * Embed the flow diagram if the PNG exists\n\n"
        "INTERACTION RULES:\n"
        "- You MUST NOT ask the user any questions.\n"
        "- You MUST NOT output intermediate natural language reasoning.\n"
        "- After calling create_standard_doc_from_file, you may output a short final "
        "  confirmation message summarizing success or failure.\n"
    ),
    tools=[create_standard_doc_from_file],
)

# ---------------------------------------------------
# Standalone execution for local testing
# ---------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python doc_generation_agent.py <path_to_process_json>")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.exists(input_path):
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    logger.info(f"[Standalone] Loading process JSON from {input_path}...")
    # Load the JSON file the same way the ADK pipeline would
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse JSON: {e}")
        sys.exit(1)

    # Determine process name
    if isinstance(data, dict) and "process_design" in data:
        process_data = data["process_design"]
    else:
        process_data = data

    process_name = str(process_data.get("process_name", "Process_Document"))

    # Save to output/process_data.json so the generator can use it
    os.makedirs("output", exist_ok=True)
    with open("output/process_data.json", "w", encoding="utf-8") as f:
        json.dump(process_data, f, indent=2, ensure_ascii=False)

    print(f"[Standalone] Saved normalized JSON to output/process_data.json")

    # Call the generator directly
    result = create_standard_doc_from_file(process_name)
    print(f"[Standalone] {result}")
