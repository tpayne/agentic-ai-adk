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
from ..uml_diagram_agent import generate_uml_diagram

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
    1.0 Executive Summary — ISO formatted, design-schema counterpart to
    _add_overview_section. Built from document_metadata + business_context
    (design_document_schema.json's shape) rather than process's flat
    purpose/scope/introduction fields.

    Per review feedback, this section needs to read as an executive
    summary specifically: the document's purpose, the business goals
    behind it, and how the rest of the document is laid out -- a
    summary only, not the exhaustive scope/objectives/business-drivers/
    assumptions/constraints detail that follows it. That detail is kept
    (dropping it wasn't asked for), just moved after a short, dedicated
    "Document Structure" paragraph that gives a returning/board-level
    reader the map before the detail, rather than making them infer the
    two-part layout from the headings as they go.
    """
    try:
        doc.add_heading("1.0 Executive Summary", level=1)

        metadata = data.get("document_metadata") or {}
        business_context = data.get("business_context") or {}

        purpose = business_context.get("purpose")
        if purpose:
            doc.add_paragraph(str(purpose))
        else:
            doc.add_paragraph("This section provides a high-level overview of the system design.")

        business_drivers = business_context.get("business_drivers")
        objectives = business_context.get("objectives")
        goal_items = [g for g in (business_drivers or objectives or []) if isinstance(g, str) and g.strip()]
        if goal_items:
            doc.add_paragraph(
                "This design is driven by the following business goals: "
                + "; ".join(goal_items[:3])
                + ("; among others." if len(goal_items) > 3 else ".")
            )

        subsection = 1

        doc.add_heading(f"1.{subsection} Document Structure", level=2)
        subsection += 1
        doc.add_paragraph(
            "This document is organized in two parts. Part I presents the "
            "business context, requirements, and architecture at a level "
            "suitable for review and approval. Part II provides the "
            "low-level design detail an implementing engineer needs to build "
            "it."
        )

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
    doc: docx.Document, stakeholders, heading: str = "2.0 Stakeholders and Responsibilities",
    subject_noun: str = "process",
) -> bool:
    """
    Stakeholders — ISO formatted. `heading` defaults to this function's
    original process-document number ("2.0"); the design document
    builder passes its own re-sequenced heading instead, since "2.0" was
    also being used verbatim by the design document's own "Architecture
    Description" section immediately afterward, producing two "2.0"
    headings in the same document.

    `subject_noun` is the word used in the body sentence below ("this
    <subject_noun>") -- defaults to "process" so every existing caller
    keeps its current wording; the design document builder passes
    "architecture" instead, since "involved in this process" read as a
    leftover process-document template string in a generated
    Architecture Specification (confirmed against a real generated
    design document).
    Returns True if it rendered anything, False on a no-op.
    """
    try:
        if not stakeholders or not isinstance(stakeholders, list):
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            f"The following is a list of key stakeholders involved in this {subject_noun}. "
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


_DIAGRAM_SIGNATURE_KEYS = {"diagram_id", "file_reference", "notation_standard", "diagram_type"}


def _looks_like_diagram_descriptor(d: dict) -> bool:
    """
    True for a dict describing a diagram (title, diagram_id,
    description, file_reference, notation_standard, diagram_type).
    Most of these are still LLM-authored bookkeeping about a diagram
    that was supposed to exist elsewhere, typically a PlantUML .puml
    source path like "docs/diagrams/lld_ire_sequence.puml" that no
    agent in this pipeline generates or renders, so the path never
    resolves to anything real. Printed as ordinary labeled fields,
    "File Reference: docs/diagrams/lld_ire_sequence.puml" reads as if
    that file exists and is one click away -- confirmed directly
    against a generated document, and flagged by a reviewer as
    "references to things that do not exist." Recognizing the shape
    lets both the dict branch and the list-of-dicts card branch below
    render only what a reader can actually use (the title and
    description) plus, where one can actually be drawn, a real
    generated image -- see _render_diagram_descriptor.

    One category IS now real: a low_level_design component's
    "sequence_flows" entries (design_document_schema.json's
    sequenceDiagramSpec) carry their own inline "participants"/"steps"
    data, so uml_diagram_agent.generate_uml_diagram can render an
    actual UML-style sequence diagram from them directly -- no external
    .puml file involved. Everything else in this doc (class diagrams,
    integration-point graphs, context/deployment views) was already
    real for the same reason: the drawable content lives in the JSON
    itself, not in a file reference.
    """
    keys = set(d.keys())
    return bool(keys & _DIAGRAM_SIGNATURE_KEYS) and ("title" in keys or "description" in keys)


def _render_diagram_descriptor(
    doc: docx.Document, d: dict, level: int, context: dict = None, system_name: str = None
) -> None:
    """
    Renders a diagram descriptor (see _looks_like_diagram_descriptor):
    title heading, description prose, and then either a REAL generated
    diagram image (via uml_diagram_agent.generate_uml_diagram, using
    whatever structural data is available in `context` -- the dict
    that directly contains this descriptor) or, if `context` doesn't
    hold anything drawable, the same honest "[... not yet generated]"
    note as before instead of a fabricated-looking file path.
    """
    title = d.get("title")
    if title:
        doc.add_heading(str(title), level=min(max(level, 1), 6))

    description = d.get("description")
    if description:
        doc.add_paragraph(str(description))

    diagram_path = generate_uml_diagram(d, context or {}, system_name=system_name)
    if diagram_path and os.path.exists(diagram_path):
        doc.add_picture(diagram_path, width=Inches(5.5))
        doc.add_paragraph()
        return

    diagram_type = d.get("diagram_type")
    label = str(diagram_type).replace("_", " ").title() if diagram_type else "Diagram"
    note = doc.add_paragraph()
    note_run = note.add_run(f"[{label} not yet generated for this document.]")
    note_run.italic = True


def _render_generic_value(
    doc: docx.Document, value, label=None, level: int = 3, system_name: str = None
) -> None:
    """
    Deterministic renderer. Chooses prose vs. a table based on what the
    content actually is, rather than always producing a table for any
    dict/list:

    - A single dict (one record's fields) renders as labeled prose --
      real architecture documents don't put a component's description
      in a bordered grid. Any field WITHIN that dict which is itself a
      structured sub-collection (a list of dicts, or a nested dict) gets
      its own heading and a recursive render, one level deeper, instead
      of being flattened into the same prose block as its siblings --
      see the "structured vs. scalar fields" split below.
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

    `level` is the Word heading level used for `label` (and propagated,
    one deeper each recursion, to any nested structured sub-collection),
    so a top-level design-doc section like "high_level_design" reads the
    way the reference process document's per-step sections do: a real
    heading hierarchy (components, then each component, then its
    fields) rather than one deeply-indented prose blob. Capped at 6 --
    Word's own practical heading depth -- so pathologically deep source
    data doesn't run past it.

    Never prints raw HTML. Never prints raw JSON/dict repr -- any nested
    dict or list value that ISN'T promoted to its own heading is still
    recursively rendered as readable indented text via _stringify_nested
    rather than str()'d directly.
    """

    heading_level = min(max(level, 1), 6)

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
            doc.add_heading(label, level=heading_level)
        for item in value:
            doc.add_paragraph(str(item), style="List Bullet")
        return

    # ---------------------------
    # List of dicts → table, or cards if too wide for a table
    # ---------------------------
    if isinstance(value, list) and all(isinstance(x, dict) for x in value):
        if label:
            doc.add_heading(label, level=heading_level)

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
            # record, then its remaining fields as labeled prose. A
            # field that is itself a structured sub-collection (e.g. a
            # component card with its own nested "interfaces" list)
            # gets promoted to its own heading + recursive render, same
            # as the dict branch above, rather than flattened prose.
            card_level = min(heading_level + 1, 6)
            for item in value:
                if _looks_like_diagram_descriptor(item):
                    _render_diagram_descriptor(doc, item, card_level, system_name=system_name)
                    doc.add_paragraph()
                    continue

                title_key = next(
                    (k for k in _TITLE_KEY_PRIORITY if item.get(k)), None
                )
                title_text = str(item.get(title_key)) if title_key else None
                if title_text:
                    doc.add_heading(title_text, level=card_level)
                structured_fields = {}
                for key in ordered_keys:
                    if key == title_key:
                        continue
                    v = item.get(key, "")
                    if v in (None, "", [], {}):
                        continue
                    if isinstance(v, list) and all(isinstance(x, dict) for x in v):
                        structured_fields[key] = v
                    elif isinstance(v, dict) and len(v) > 1:
                        structured_fields[key] = v
                    else:
                        text = _stringify_nested(v)
                        _add_prose_field(doc, key.replace("_", " ").title(), text)
                doc.add_paragraph()  # spacer after the card's own fields
                for key, v in structured_fields.items():
                    if isinstance(v, dict) and _looks_like_diagram_descriptor(v):
                        _render_diagram_descriptor(
                            doc, v, card_level + 1, context=item, system_name=system_name
                        )
                    elif isinstance(v, list) and v and all(_looks_like_diagram_descriptor(x) for x in v):
                        if key:
                            doc.add_heading(key.replace("_", " ").title(), level=min(card_level + 1, 6))
                        for diag in v:
                            _render_diagram_descriptor(
                                doc, diag, card_level + 2, context=item, system_name=system_name
                            )
                    else:
                        _render_generic_value(
                            doc, v, label=key.replace("_", " ").title(), level=card_level + 1,
                            system_name=system_name,
                        )
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
        if _looks_like_diagram_descriptor(value):
            _render_diagram_descriptor(doc, value, heading_level, system_name=system_name)
            return

        if label:
            doc.add_heading(label, level=heading_level)

        # Split this dict's fields into "structured" sub-collections
        # (a nested list-of-dicts, or a nested dict with its own several
        # fields) versus everything else (scalars, short lists, plain
        # strings). A structured field gets promoted to its own heading
        # and a recursive _render_generic_value call one level deeper,
        # rather than being flattened into indented text via
        # _stringify_nested alongside its scalar siblings. Confirmed
        # real case: design_data.json's high_level_design/
        # low_level_design hold nested lists like "components" or
        # "interfaces" -- each with several fields of its own -- and
        # without this split they rendered as one long indented prose
        # block under a single "Components:" label instead of reading
        # like the process document's per-step sections (a real heading
        # per record, then that record's own fields underneath).
        scalar_items = {}
        structured_items = {}
        for k, v in value.items():
            if v in (None, "", [], {}):
                continue
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                structured_items[k] = v
            elif isinstance(v, dict) and len(v) > 1:
                structured_items[k] = v
            else:
                scalar_items[k] = v

        # Merge sibling keys whose rendered text is exactly identical
        # into a single labeled field, instead of printing the same
        # content twice. Confirmed real case: a design doc's
        # low_level_design has both "error_handling_strategy" and
        # "exception_handling_strategy" keys holding byte-identical
        # text -- the source JSON has two synonymous fields describing
        # the same thing. Only non-empty text is eligible to merge, so
        # two unrelated blank/absent fields never get collapsed into one
        # misleading field.
        texts = {k: _stringify_nested(v) for k, v in scalar_items.items()}
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
        for k in scalar_items.keys():
            if k not in duplicate_of:
                merged_labels[k] = [k]
        for k, dup_target in duplicate_of.items():
            merged_labels[dup_target].append(k)

        for k in scalar_items.keys():
            if k in duplicate_of:
                continue
            combined_label = " / ".join(
                kk.replace("_", " ").title() for kk in merged_labels[k]
            )
            _add_prose_field(doc, combined_label, texts[k])

        if scalar_items:
            doc.add_paragraph()

        for k, v in structured_items.items():
            # A structured field that is itself a diagram descriptor
            # (a "diagram" dict) or a list of them (a "diagrams" list)
            # gets rendered directly with THIS dict (`value`) passed as
            # its sibling context -- e.g. a class_design dict's own
            # "classes" list is exactly what its "diagram" field needs
            # to actually draw from. Recursing generically here would
            # lose that context, since _render_generic_value has no way
            # to see `value` once called on `v` alone.
            if isinstance(v, dict) and _looks_like_diagram_descriptor(v):
                _render_diagram_descriptor(
                    doc, v, heading_level + 1, context=value, system_name=system_name
                )
                continue

            if isinstance(v, list) and v and all(_looks_like_diagram_descriptor(x) for x in v):
                doc.add_heading(k.replace("_", " ").title(), level=min(heading_level + 1, 6))
                for diag in v:
                    _render_diagram_descriptor(
                        doc, diag, heading_level + 2, context=value, system_name=system_name
                    )
                continue

            _render_generic_value(
                doc, v, label=k.replace("_", " ").title(), level=heading_level + 1,
                system_name=system_name,
            )

        return

    # ---------------------------
    # Fallback
    # ---------------------------
    doc.add_paragraph(str(value))
