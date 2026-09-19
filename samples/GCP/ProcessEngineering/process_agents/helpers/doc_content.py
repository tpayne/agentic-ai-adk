# process_agents/helpers/doc_content.py

import docx
import os
import json
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

import traceback
import logging

from .doc_structure import (
    _add_header,
    _add_bullet,
    apply_iso_table_formatting,
    add_iso_page_break,
)

from ..step_diagram_agent import generate_step_diagram_for_step

logger = logging.getLogger("ProcessArchitect.DocContent")


# ============================================================
# 1.0 PROCESS OVERVIEW
# ============================================================

def _add_overview_section(doc: docx.Document, data: dict) -> None:
    """
    1.0 Process Overview — ISO formatted.
    """
    try:
        doc.add_heading("1.0 Process Overview", level=1)

        introduction = data.get("introduction")
        description = data.get("description") or data.get("process_description")

        if introduction:
            doc.add_paragraph(str(introduction))
        elif description:
            doc.add_paragraph(str(description))
        else:
            doc.add_paragraph("This section provides a high-level overview of the business process.")

        subsection = 1

        # --- Assumptions ---
        assumptions = data.get("assumptions")
        if isinstance(assumptions, list) and assumptions:
            doc.add_heading(f"1.{subsection} Assumptions", level=2)
            subsection += 1
            for item in assumptions:
                doc.add_paragraph(item, style="List Bullet")

        # --- Constraints ---
        constraints = data.get("constraints")
        if isinstance(constraints, list) and constraints:
            doc.add_heading(f"1.{subsection} Constraints", level=2)
            subsection += 1
            for item in constraints:
                doc.add_paragraph(item, style="List Bullet")

        # --- Purpose, Scope, Industry ---
        ordered = [
            ("purpose", "Purpose"),
            ("scope", "Scope"),
            ("industry_sector", "Industry Sector"),
        ]

        for key, label in ordered:
            value = data.get(key)
            if value:
                doc.add_heading(f"1.{subsection} {label}", level=2)
                subsection += 1
                doc.add_paragraph(str(value))

        # --- Additional metadata ---
        for key in ["out_of_scope", "business_unit", "owner"]:
            if key in data:
                p = doc.add_paragraph()
                r = p.add_run(f"{key.replace('_', ' ').title()}: ")
                r.bold = True
                p.add_run(str(data.get(key)))

    except Exception:
        traceback.print_exc()


# ============================================================
# 1.0 DESIGN DOCUMENT OVERVIEW (design schema counterpart)
# ============================================================

def _add_design_overview_section(doc: docx.Document, data: dict) -> None:
    """
    1.0 Document Overview — ISO formatted, design-schema counterpart to
    _add_overview_section. Built from document_metadata + business_context
    (design_document_schema.json's shape) rather than process's flat
    purpose/scope/introduction fields.
    """
    try:
        doc.add_heading("1.0 Document Overview", level=1)

        metadata = data.get("document_metadata") or {}
        business_context = data.get("business_context") or {}

        purpose = business_context.get("purpose")
        if purpose:
            doc.add_paragraph(str(purpose))
        else:
            doc.add_paragraph("This section provides a high-level overview of the system design.")

        subsection = 1

        scope = business_context.get("scope")
        if scope:
            doc.add_heading(f"1.{subsection} Scope", level=2)
            subsection += 1
            doc.add_paragraph(str(scope))

        for key, label in [
            ("objectives", "Objectives"),
            ("business_drivers", "Business Drivers"),
            ("assumptions", "Assumptions"),
            ("constraints", "Constraints"),
        ]:
            value = business_context.get(key)
            if isinstance(value, list) and value:
                doc.add_heading(f"1.{subsection} {label}", level=2)
                subsection += 1
                for item in value:
                    doc.add_paragraph(str(item), style="List Bullet")

        # Document identity metadata
        for key, label in [
            ("system_name", "System Name"),
            ("industry_sector", "Industry Sector"),
            ("document_type", "Document Type"),
            ("template_standard", "Template Standard"),
        ]:
            value = metadata.get(key)
            if value:
                p = doc.add_paragraph()
                r = p.add_run(f"{label}: ")
                r.bold = True
                p.add_run(str(value))

    except Exception:
        traceback.print_exc()

def _add_stakeholders_section(
    doc: docx.Document, stakeholders, heading: str = "2.0 Stakeholders and Responsibilities"
) -> bool:
    """
    Stakeholders — ISO formatted. `heading` defaults to this function's
    original process-document number ("2.0"); the design document
    builder passes its own re-sequenced heading instead, since "2.0" was
    also being used verbatim by the design document's own "Architecture
    Description" section immediately afterward, producing two "2.0"
    headings in the same document.
    Returns True if it rendered anything, False on a no-op.
    """
    try:
        if not stakeholders or not isinstance(stakeholders, list):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "The following is a list of key stakeholders involved in this process. "
            "Understanding their roles and responsibilities is crucial for successful implementation."
        )

        # Simple list
        if all(isinstance(s, str) for s in stakeholders):
            for s in stakeholders:
                doc.add_paragraph(str(s), style="List Bullet")
            doc.add_paragraph()
            return True

        # Table
        table = doc.add_table(rows=1, cols=2)
        hdr = table.rows[0].cells
        hdr[0].text = "Stakeholder"
        hdr[1].text = "Responsibilities"

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

            row = table.add_row().cells
            row[0].text = str(name)
            if isinstance(responsibilities, list):
                row[1].text = "\n".join(str(x) for x in responsibilities)
            else:
                row[1].text = str(responsibilities)

        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True

    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 3.0 PROCESS WORKFLOW
# ============================================================
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

def _add_process_steps_section(doc: docx.Document, steps) -> None:
    """
    Hybrid prose + bullet renderer for top-level process steps (3.x).
    No tables. No HTML. Deterministic formatting.
    """
    logger.debug("Rendering process workflow (prose + bullets)…")

    if not isinstance(steps, list) or not steps:
        return

    doc.add_heading("3.0 Process Workflow", level=1)
    doc.add_paragraph(
        "The following is a list of key steps in the process workflow."
    )

    INTRO = {
        "inputs": "The following inputs are required for this step:",
        "outputs": "This step produces the following outputs:",
        "success_criteria": "Success for this step is measured by:",
        "process_triggers": "This step is initiated by:",
        "process_end_conditions": "This step is considered complete when:",
        "dependencies": "This step depends on the following:",
        "deliverables": "This step produces the following deliverables:",
        "governance_requirements": "The following governance requirements apply:",
        "risks_and_controls": "The following risks and controls apply:",
        "step_risks_and_controls": "The following risks and controls apply:",
        "change_management": "The following change management rules apply:",
        "continuous_improvement": "The following continuous improvement practices apply:",
        "estimated_duration": "The estimated duration for this step is:",
        "process_owner": "The following process owner is accountable:",
        "responsible_party": "The following parties are responsible for this step:",
    }

    def expand_value(doc, value, indent=False):
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, list):
                    _add_bullet(doc, f"{k.replace('_',' ').title()}:", indent)
                    for item in v:
                        _add_bullet(doc, item, indent=True)
                else:
                    _add_bullet(doc, f"{k.replace('_',' ').title()}: {v}", indent)

        elif isinstance(value, list):
            for item in value:
                expand_value(doc, item, indent)

        else:
            _add_bullet(doc, value, indent)

    for s_idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue

        step_name = step.get("step_name", f"Step {s_idx}")

        if s_idx > 1:
            add_iso_page_break(doc)

        doc.add_heading(f"3.{s_idx} {step_name}", level=2)

        def prose(label, value):
            if not value:
                return
            doc.add_heading(f"{label}:", level=4)
            doc.add_paragraph(str(value))

        prose("Description", step.get("description"))
        prose("Purpose", step.get("purpose"))
        prose("Scope", step.get("scope"))

        def bullets(field_label, json_key):
            value = step.get(json_key) or step.get(f"step_{json_key}")
            if not value:
                return

            doc.add_heading(f"{field_label}:", level=4)
            doc.add_paragraph(INTRO[json_key])
            expand_value(doc, value)

        bullets("Inputs", "inputs")
        bullets("Outputs", "outputs")
        bullets("Success Criteria", "success_criteria")
        bullets("Process Triggers", "process_triggers")
        bullets("Process End Conditions", "process_end_conditions")
        bullets("Dependencies", "dependencies")
        bullets("Deliverables", "deliverables")
        bullets("Governance Requirements", "governance_requirements")
        bullets("Risks and Controls", "risks_and_controls")
        bullets("Change Management", "change_management")
        bullets("Continuous Improvement", "continuous_improvement")
        bullets("Estimated Duration", "estimated_duration")
        bullets("Process Owner", "process_owner")
        bullets("Responsible Parties", "responsible_party")

        subprocess_json = step.get("subprocess")
        if isinstance(subprocess_json, dict):
            _add_subprocess_section(doc, s_idx, step_name, subprocess_json)

        doc.add_paragraph()

# ============================================================
# SUBPROCESS RENDERING (3.x.y.z)
# ============================================================

def _add_subprocess_section(doc, step_index: int, step_name: str, subprocess_json: dict) -> None:
    """
    Hybrid prose + bullet renderer for subprocess steps (3.x.y).
    Restores diagrams. No tables. No HTML.
    """
    flow = subprocess_json.get("subprocess_flow")
    if not isinstance(flow, list) or not flow:
        return

    add_iso_page_break(doc)

    doc.add_heading(
        f'Required Sub Process(es) for the Step "{step_name}"',
        level=3,
    )
    doc.add_paragraph(
        f'The following details the subprocess flows for the step "{step_name}".'
    )

    _add_step_diagram_if_available(doc, step_name, subprocess_json)

    INTRO = {
        "inputs": "The following inputs are required for this subprocess:",
        "outputs": "This subprocess produces the following outputs:",
        "success_criteria": "Success for this subprocess is measured by:",
        "triggers": "This subprocess is initiated by:",
        "end_conditions": "This subprocess is considered complete when:",
        "dependencies": "This subprocess depends on the following:",
        "governance_requirements": "The following governance requirements apply:",
        "risks_and_controls": "The following risks and controls apply:",
        "step_risks_and_controls": "The following risks and controls apply:",
        "change_management": "The following change management rules apply:",
        "continuous_improvement": "The following continuous improvement practices apply:",
        "estimated_duration": "The estimated duration for this subprocess is:",
        "process_owner": "The following process owner is accountable:",
        "responsible_party": "The following parties are responsible for this subprocess:",
    }

    def expand_value(doc, value, indent=False):
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, list):
                    _add_bullet(doc, f"{k.replace('_',' ').title()}:", indent)
                    for item in v:
                        _add_bullet(doc, item, indent=True)
                else:
                    _add_bullet(doc, f"{k.replace('_',' ').title()}: {v}", indent)

        elif isinstance(value, list):
            for item in value:
                expand_value(doc, item, indent)

        else:
            _add_bullet(doc, value, indent)

    for sub_idx, sub in enumerate(flow, start=1):
        if not isinstance(sub, dict):
            continue

        sub_name = sub.get("substep_name", f"Sub-step {sub_idx}")

        add_iso_page_break(doc)
        doc.add_heading(f"3.{step_index}.{sub_idx} {sub_name}", level=4)

        doc.add_paragraph(
            f"This subprocess describes the activities required to complete '{sub_name}'."
        )

        diagram = sub.get("diagram")
        if diagram and os.path.exists(diagram):
            doc.add_picture(diagram, width=Inches(6))
            doc.add_paragraph()

        def prose(label, value):
            if not value:
                return
            doc.add_heading(f"{label}:", level=5)
            doc.add_paragraph(str(value))

        prose("Description", sub.get("description"))
        prose("Purpose", sub.get("purpose"))
        prose("Scope", sub.get("scope"))

        def bullets(field_label, json_key):
            value = sub.get(json_key) or sub.get(f"step_{json_key}")
            if not value:
                return

            doc.add_heading(f"{field_label}:", level=5)
            doc.add_paragraph(INTRO[json_key])
            expand_value(doc, value)

        bullets("Inputs", "inputs")
        bullets("Outputs", "outputs")
        bullets("Success Criteria", "success_criteria")
        bullets("Triggers", "triggers")
        bullets("End Conditions", "end_conditions")
        bullets("Dependencies", "dependencies")
        bullets("Governance Requirements", "governance_requirements")
        bullets("Risks and Controls", "risks_and_controls")
        bullets("Change Management", "change_management")
        bullets("Continuous Improvement", "continuous_improvement")
        bullets("Estimated Duration", "estimated_duration")
        bullets("Process Owner", "process_owner")
        bullets("Responsible Party", "responsible_party")

        doc.add_paragraph()


def _stringify_nested(value, indent: int = 0) -> str:
    """
    Renders a (possibly nested) dict/list/scalar into readable, indented
    plain text suitable for a single Word table cell.

    This exists because a bare str(v) on a dict or a list of dicts prints
    Python's repr of it (e.g. "{'title': 'System Context', 'description':
    ...}"), which is exactly what leaked raw dict/JSON-looking text into
    generated documents: _render_generic_value's table branches used to
    call str(v) directly on any cell value that wasn't a list of plain
    scalars, and design_document_schema.json has many fields nested one
    or two levels deeper than the flatter process schema (diagram
    references, decision records, traceability matrices, change logs,
    approval workflows, tech stacks, etc.), so this path is hit far more
    often for design documents.

    Instead, this recurses: a nested dict becomes "Key: value" lines (one
    per key, title-cased), a nested list becomes "- item" lines, and each
    level of nesting is indented -- never Python's dict/list repr.

    Also handles a JSON *string* value, not just a real dict/list: some
    design_document_schema.json fields (e.g. an interface contract's
    request_schema/response_schema) hold a JSON Schema document that was
    serialized to a string before being written into design_data.json,
    rather than kept as a real nested object. Left alone, that string is
    scalar as far as this function's type checks are concerned, so it
    fell through to the plain str(value) below and printed the raw,
    escaped JSON text verbatim -- confirmed against a real generated
    document's interface/component fields, which showed literal
    '{\\"$schema\\":\\"http://json-schema.org/draft-07/schema#\\"...'
    text. Detecting and parsing it here means it renders exactly like
    any other nested field instead of as raw escaped text.
    """
    pad = "  " * indent

    if value is None or value == "" or value == [] or value == {}:
        return ""

    if isinstance(value, str):
        stripped = value.strip()
        if len(stripped) > 1 and stripped[0] in "{[" and stripped[-1] in "}]":
            parsed = None
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                pass
            if not isinstance(parsed, (dict, list)):
                # Confirmed real case: request_schema/response_schema
                # fields hold DOUBLE-encoded JSON -- the string's actual
                # characters include literal backslashes before every
                # quote (e.g. '{\\"$schema\\":...}'), because the JSON
                # Schema document was serialized to a string, and THAT
                # string was itself embedded as JSON, escaping every
                # quote a second time. A single json.loads() on it fails
                # ("Expecting property name enclosed in double quotes")
                # since the leading `{` isn't followed by a real quote.
                # Wrapping it in an extra pair of quotes and parsing that
                # first undoes exactly one layer of JSON string escaping
                # (the standard way to un-escape \" -> ", \\n -> newline,
                # etc. without a fragile manual .replace()), producing
                # the singly-encoded JSON text underneath, which then
                # parses normally.
                try:
                    unescaped = json.loads('"' + stripped + '"')
                    parsed = json.loads(unescaped)
                except (ValueError, TypeError):
                    parsed = None
            if isinstance(parsed, (dict, list)) and parsed:
                return _stringify_nested(parsed, indent)

    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if v in (None, "", [], {}):
                continue
            key_label = str(k).replace("_", " ").title()
            # Always recurse, even for a plain string: a string value can
            # itself be JSON-encoded (see the string-handling branch
            # above), and only _stringify_nested knows how to detect and
            # expand that. The old version of this loop only recursed
            # for values that were ALREADY a dict/list and otherwise
            # inlined the raw value directly (f"{key}: {v}"), which is
            # exactly why a JSON-string field still printed raw escaped
            # JSON even after this function learned to parse such
            # strings -- that parsing only ran when _stringify_nested was
            # called on the string directly, never when the string was
            # one field inside a surrounding dict, which is the normal
            # case (e.g. api_specifications[i].request_schema).
            nested = _stringify_nested(v, indent + 1)
            if not nested:
                continue
            if "\n" in nested:
                lines.append(f"{pad}{key_label}:")
                lines.append(nested)
            else:
                lines.append(f"{pad}{key_label}: {nested}")
        return "\n".join(lines)

    if isinstance(value, list):
        lines = []
        for item in value:
            nested = _stringify_nested(item, indent + 1)
            if not nested:
                continue
            if "\n" in nested:
                lines.append(f"{pad}-")
                lines.append(nested)
            else:
                lines.append(f"{pad}- {nested}")
        return "\n".join(lines)

    return str(value)


def _add_prose_field(doc: docx.Document, label_text: str, text_value: str, indent: int = 0) -> None:
    """
    Renders one "Label: value" field as a normal paragraph (bold label,
    plain text) instead of a table row. Multi-line values (from
    _stringify_nested's indented dict/list text) get real paragraph line
    breaks via add_break(), not literal "\\n" characters sitting inside
    a single run -- Word does not render an embedded "\\n" character as
    a line break, it just gets collapsed/ignored.

    This exists because a single nested dict was previously always
    rendered as a bordered, grey-header "Field / Value" table no matter
    how simple or narrative its content (e.g. a component description,
    a business-context block) -- a reviewer's direct feedback on a
    generated document was "too many tables ... too heavy ... far too
    much cognitive load," and a large fraction of this document's tables
    turned out to be exactly this: a single dict's fields dumped into a
    2-column grid purely because the fallback renderer only knew how to
    produce tables. Plain labeled paragraphs read the way a real
    architecture document does for this kind of content.
    """
    if not text_value:
        return
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.left_indent = Inches(0.25 * indent)
    lines = text_value.split("\n")
    label_run = p.add_run(f"{label_text}:")
    label_run.bold = True
    if len(lines) == 1:
        p.add_run(f" {lines[0]}")
    else:
        for line in lines:
            p.add_run().add_break()
            p.add_run(line)


def _render_generic_value(doc: docx.Document, value, label=None) -> None:
    """
    Deterministic renderer. Chooses prose vs. a table based on what the
    content actually is, rather than always producing a table for any
    dict/list:

    - A single dict (one record's fields) renders as labeled prose --
      real architecture documents don't put a component's description
      in a bordered grid.
    - A list of dicts with FEW distinct fields (<=4 -- e.g. Term/
      Definition, Risk/Control) still renders as a compact table, since
      that genuinely is tabular, repeated, scannable data.
    - A list of dicts with MANY distinct fields (>4 -- e.g. a 9-column
      Architecture Decisions list, an 8-column Risk Register) renders as
      a sequence of prose "cards" instead: one heading per record (its
      title/id/name, whichever is present) followed by its remaining
      fields as labeled prose. A table that wide is unreadable at any
      column width; this is how real ADR/risk-register tooling presents
      the same data.

    Never prints raw HTML. Never prints raw JSON/dict repr -- any nested
    dict or list value is recursively rendered as readable indented text
    via _stringify_nested rather than str()'d directly.
    """

    # ---------------------------
    # Simple string → paragraph
    # ---------------------------
    if isinstance(value, str):
        p = doc.add_paragraph()
        if label:
            r = p.add_run(f"{label}: ")
            r.bold = True
        p.add_run(value)
        return

    # ---------------------------
    # List of simple values
    # ---------------------------
    if isinstance(value, list) and all(isinstance(x, (str, int, float)) for x in value):
        if label:
            doc.add_heading(label, level=3)
        for item in value:
            doc.add_paragraph(str(item), style="List Bullet")
        return

    # ---------------------------
    # List of dicts → table, or cards if too wide for a table
    # ---------------------------
    if isinstance(value, list) and all(isinstance(x, dict) for x in value):
        if label:
            doc.add_heading(label, level=3)

        # Collect all keys
        all_keys = set()
        for item in value:
            all_keys.update(item.keys())

        ordered_keys = sorted(all_keys)

        _TITLE_KEY_PRIORITY = (
            "title", "name", "component_name", "module_name", "view_name",
            "viewpoint_name", "characteristic", "id", "risk", "term",
        )

        if len(ordered_keys) > 4:
            # Too many distinct fields for a readable table (a 9-column
            # Architecture Decisions table or an 8-column Risk Register
            # is unreadable regardless of column width) -- render one
            # prose card per record instead: a heading naming the
            # record, then its remaining fields as labeled prose.
            for item in value:
                title_key = next(
                    (k for k in _TITLE_KEY_PRIORITY if item.get(k)), None
                )
                title_text = str(item.get(title_key)) if title_key else None
                if title_text:
                    doc.add_heading(title_text, level=4)
                for key in ordered_keys:
                    if key == title_key:
                        continue
                    v = item.get(key, "")
                    if v in (None, "", [], {}):
                        continue
                    text = _stringify_nested(v)
                    _add_prose_field(doc, key.replace("_", " ").title(), text)
                doc.add_paragraph()  # spacer between cards
            return

        table = doc.add_table(rows=1, cols=len(ordered_keys))
        hdr = table.rows[0].cells
        for i, key in enumerate(ordered_keys):
            hdr[i].text = key.replace("_", " ").title()

        for item in value:
            row = table.add_row().cells
            for i, key in enumerate(ordered_keys):
                v = item.get(key, "")
                row[i].text = _stringify_nested(v)

        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return

    # ---------------------------
    # Dict → labeled prose (not a table)
    # ---------------------------
    if isinstance(value, dict):
        if label:
            doc.add_heading(label, level=3)

        # Merge sibling keys whose rendered text is exactly identical
        # into a single labeled field, instead of printing the same
        # content twice. Confirmed real case: a design doc's
        # low_level_design has both "error_handling_strategy" and
        # "exception_handling_strategy" keys holding byte-identical
        # text -- the source JSON has two synonymous fields describing
        # the same thing. Only non-empty text is eligible to merge, so
        # two unrelated blank/absent fields never get collapsed into one
        # misleading field.
        texts = {k: _stringify_nested(v) for k, v in value.items()}
        first_key_for_text = {}
        duplicate_of = {}
        for k, text in texts.items():
            if not text:
                continue
            if text not in first_key_for_text:
                first_key_for_text[text] = k
            elif first_key_for_text[text] != k:
                duplicate_of[k] = first_key_for_text[text]

        merged_labels = {}
        for k in value.keys():
            if k not in duplicate_of:
                merged_labels[k] = [k]
        for k, dup_target in duplicate_of.items():
            merged_labels[dup_target].append(k)

        for k in value.keys():
            if k in duplicate_of:
                continue
            combined_label = " / ".join(
                kk.replace("_", " ").title() for kk in merged_labels[k]
            )
            _add_prose_field(doc, combined_label, texts[k])

        doc.add_paragraph()
        return

    # ---------------------------
    # Fallback
    # ---------------------------
    doc.add_paragraph(str(value))
