# process_agents/helpers/doc_governance.py

import docx
import traceback
import logging

from .doc_structure import _add_header, _add_bullet
from .doc_content import _render_generic_value

logger = logging.getLogger("ProcessArchitect.DocGovernance")

def _add_governance_requirements_section(doc, items):
    """Adds Governance Requirements as bullets, or a 'none' message."""
    doc.add_heading("12.0 Governance Requirements", level=1)
 
    if not items:
        doc.add_paragraph("There are no governance requirements to document.", style="Normal")
        return
    else:
        doc.add_paragraph("There following are the list of governance requirements used in this process.", style="Normal")

    for item in items:
        _add_bullet(doc, item)

def _add_risks_and_controls_section(doc, items):
    """Adds Risks & Controls as a 2‑column table."""

    doc.add_heading("13.0 Risks and Controls", level=1)
    doc.add_paragraph("The following risks and associated controls apply to this process.")

    if not items:
        return

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"

    # Header row
    hdr = table.rows[0].cells
    hdr[0].text = "Risk"
    hdr[1].text = "Control"

    # Bold headers
    for cell in hdr:
        for p in cell.paragraphs:
            for run in p.runs:
                run.bold = True

    # Data rows
    for rc in items:
        row = table.add_row().cells
        row[0].text = str(rc.get("risk", ""))
        row[1].text = str(rc.get("control", ""))

def _add_process_triggers_section(doc, items):
    """Adds Process Triggers as bullets, or a 'none' message."""
    doc.add_heading("14.0 Process Triggers", level=1)

    if not items:
        doc.add_paragraph("There are no process triggers to document.", style="Normal")
        return
    else:
        doc.add_paragraph("There following are triggers that kick processes off.", style="Normal")

    for item in items:
        _add_bullet(doc, item)

def _add_process_end_conditions_section(doc, items):
    """Adds Process End Conditions as bullets, or a 'none' message."""
    doc.add_heading("15.0 Process End Conditions", level=1)

    if not items:
        doc.add_paragraph("There are no process end conditions to document.", style="Normal")
        return
    else:
        doc.add_paragraph("There following are a list of the process end conditions.", style="Normal")

    for item in items:
        _add_bullet(doc, item)

def _add_change_management_section(doc, items):
    """Adds Change Management details as bullets, or a 'none' message."""
    doc.add_heading("16.0 Change Management", level=1)

    if not items:
        doc.add_paragraph("There are no change management items to document.", style="Normal")
        return
    else:
        doc.add_paragraph("There following are list of the change management procedures.", style="Normal")

    for cm in items:
        if isinstance(cm, dict):
            crp = cm.get("change_request_process")
            vr = cm.get("versioning_rules")

            if crp:
                _add_bullet(doc, f"Change Request Process: {crp}")
            if vr:
                _add_bullet(doc, f"Versioning Rules: {vr}")

def _add_continuous_improvement_section(doc, items):
    """Adds Continuous Improvement details as bullets, or a 'none' message."""
    doc.add_heading("17.0 Continuous Improvement", level=1)

    if not items:
        doc.add_paragraph("There are no continuous improvement items to document.", style="Normal")
        return
    else:
        doc.add_paragraph("The following are the items used for continuous improvement.", style="Normal")

    for ci in items:
        if not isinstance(ci, dict):
            continue

        freq = ci.get("review_frequency")
        inputs = ci.get("improvement_inputs", [])

        if freq:
            _add_bullet(doc, f"Review Frequency: {freq}")

        if inputs:
            _add_header(doc, "Improvement Inputs:")
            for inp in inputs:
                _add_bullet(doc, inp)

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

def _add_critical_success_factors_section(doc, factors):
    """Adds Critical Success Factors as a TABLE, matching the metrics format."""
    if not factors:
        return
    
    doc.add_heading('6.0 Critical Success Factors (CSF)', level=1)
    doc.add_paragraph(
        f"The following is a list of key CSFs associated with this process. "
    )
    
    # Create table: 2 columns (Name and Description)
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid' # Matches the standard bordered look
    
    # Header Row
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Success Factor'
    hdr_cells[1].text = 'Description'
    
    # Apply Bold to Headers
    for cell in hdr_cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True

    # Fill Data
    for factor in factors:
        row_cells = table.add_row().cells
        row_cells[0].text = str(factor.get("name", ""))
        row_cells[1].text = str(factor.get("description", ""))

def _add_critical_failure_factors_section(doc, factors):
    """Adds Critical Failure Factors as a TABLE, matching the metrics format."""
    if not factors:
        return
    
    doc.add_heading('7.0 Critical Failure Factors (CFF)', level=1)
    doc.add_paragraph(
        f"The following is a list of key CFFs associated with this process. "
    )
    
    # Create table: 2 columns
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    
    # Header Row
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Failure Factor'
    hdr_cells[1].text = 'Description'
    
    # Apply Bold to Headers
    for cell in hdr_cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True

    # Fill Data
    for factor in factors:
        row_cells = table.add_row().cells
        row_cells[0].text = str(factor.get("name", ""))
        row_cells[1].text = str(factor.get("description", ""))


def _add_reporting_and_analytics(doc: docx.Document, ra) -> None:
    try:
        if ra is None:
            return

        doc.add_heading("8.0 Reporting and Analytics", level=1)
        doc.add_paragraph(
            "The following are key reporting and analytics associated with this process."
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

        # Case 1: Dictionary
        if isinstance(ra, dict):
            table = doc.add_table(rows=1, cols=2)
            table.style = "Table Grid"
            hdr = table.rows[0].cells
            hdr[0].text = "Metric"
            hdr[1].text = "Description"

            for key, value in ra.items():
                row = table.add_row().cells
                row[0].text = key.replace("_", " ").title()
                row[1].text = flatten_value(value)

            doc.add_paragraph()
            return

        # Case 2: List of simple values
        if isinstance(ra, list) and all(isinstance(x, (str, int, float)) for x in ra):
            for item in ra:
                doc.add_paragraph(str(item), style="List Bullet")
            doc.add_paragraph()
            return

        # Case 3: List of dicts (your main case)
        if isinstance(ra, list) and all(isinstance(x, dict) for x in ra):
            # Collect all keys
            all_keys = set()
            for item in ra:
                all_keys.update(item.keys())

            # Force correct column order
            ordered_keys = []
            if "metric" in all_keys:
                ordered_keys.append("metric")
            if "description" in all_keys:
                ordered_keys.append("description")

            # Add any remaining keys after the required ones
            remaining = [k for k in all_keys if k not in ("metric", "description")]
            ordered_keys.extend(sorted(remaining))

            # Build table
            table = doc.add_table(rows=1, cols=len(ordered_keys))
            table.style = "Table Grid"

            # Header row
            hdr = table.rows[0].cells
            for idx, key in enumerate(ordered_keys):
                hdr[idx].text = key.replace("_", " ").title()

            # Data rows
            for item in ra:
                row = table.add_row().cells
                for idx, key in enumerate(ordered_keys):
                    val = item.get(key, "")
                    row[idx].text = flatten_value(val)

            doc.add_paragraph()
            return

        # Fallback: Mixed or nested structures
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
