"""ISO-style Word document structural helpers (tables, page breaks, version
history, table of contents). Ported verbatim from the ADK sample's
process_agents/common/helpers/doc_structure.py -- pure python-docx, no ADK
dependency.
"""

import docx
from docx.shared import Pt, Inches, Emu
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from datetime import datetime
import re
import traceback
import logging

logger = logging.getLogger("ProcessArchitect.DocStructure")

# ------------------------------------------------------------------
# Column width heuristics for apply_iso_table_formatting.
#
# Generated tables mix short categorical/ID-style columns (Id, Status,
# Date, Priority, Severity, Likelihood, Owner, Role, Category, Type,
# Method, Frequency, Target, Metric, Characteristic) with long free-text
# prose columns (Description, Decision, Consequences, Context,
# Rationale, Mitigation, Notes, Instruction, Definition). Splitting a
# table's width EQUALLY across every column -- which is what happens if
# no explicit width is set -- squeezes prose columns in a wide table
# down to well under an inch, forcing long sentences to wrap across many
# short lines and making the table effectively unreadable. These weights
# let prose columns claim several times the width of a short categorical
# column instead.
# ------------------------------------------------------------------
_NARROW_COLUMN_KEYWORDS = {
    "id", "status", "date", "version", "priority", "severity",
    "likelihood", "impact", "type", "category", "owner", "role",
    "author", "method", "frequency", "target", "metric",
    "characteristic", "sub characteristic",
}
_WIDE_COLUMN_KEYWORDS = {
    "description", "decision", "consequences", "context", "rationale",
    "mitigation", "notes", "instruction", "definition", "alternatives",
    "alternatives considered", "responsibilities", "objectives",
    "acceptance criteria", "measure method", "measurement method",
    "applicability", "requirement",
}


def _column_width_weight(header_text: str) -> float:
    key = header_text.strip().lower()
    if key in _NARROW_COLUMN_KEYWORDS:
        return 1.3
    if any(kw in key for kw in _WIDE_COLUMN_KEYWORDS):
        return 2.6
    return 1.5


def _set_repeat_header_row(row) -> None:
    """Marks a table row to repeat as a header on every page it spans."""
    tr = row._tr
    trPr = tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)


def _force_fixed_table_layout(table) -> None:
    """
    Forces Word to honor explicit column widths instead of silently
    auto-fitting to content.
    """
    tbl = table._tbl
    tblPr = tbl.tblPr
    for existing in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(existing)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)


def _add_header(doc, label):
    """Adds a bold section sub-header with standard spacing."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(0)
    p.add_run(label).bold = True
    return p


def _add_bullet(doc, text, indent=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    if indent:
        p.paragraph_format.left_indent = Inches(0.3)
    p.add_run(f"• {text}")


def _item_text(item, *content_keys: str) -> str:
    """
    Returns a displayable string for one entry of a list field the source
    JSON might represent as a plain string (the shape several renderers
    here were written against, matching the ADK original's own
    process_schema.json template for fields like constraints/
    governance_requirements/process_triggers) OR as an
    {"id": ..., "<content_key>": ...} traceability-style object -- the
    shape this port's own agents fall back to improvising when a field's
    template hint doesn't pin one down precisely, confirmed directly
    against real generated output (e.g. constraints as
    {"id": "CON-001", "description": "..."}).

    Passing a bare dict straight to doc.add_paragraph()/_add_bullet()
    doesn't raise -- python-docx silently iterates a dict's KEYS as if it
    were a string of characters, producing garbage like "iddescription".
    This is the fix: try each of `content_keys`, in priority order, for
    the dict's actual content; fall back to every non-"id" value joined
    together if none match, so content is never silently dropped even
    when the content key doesn't match any of the ones a caller guessed.
    """
    if isinstance(item, dict):
        for key in content_keys:
            value = item.get(key)
            if value:
                return str(value)
        remaining = [str(v) for k, v in item.items() if k != "id" and v not in (None, "", [], {})]
        if remaining:
            return "; ".join(remaining)
        return ""
    return str(item)


def _set_cell_bullets(cell, value, empty_text: str = "—") -> None:
    """
    Fills a table cell with bulleted content. A list value becomes one
    "• " line per item; a plain string value becomes a single "• " line.
    An empty/missing value renders as a plain em dash with NO bullet.
    """
    cell.text = ""  # clears the single empty default paragraph
    first_paragraph = cell.paragraphs[0]

    items = value if isinstance(value, list) else ([value] if value not in (None, "") else [])
    items = [str(item) for item in items if str(item).strip()]

    if not items:
        first_paragraph.add_run(empty_text)
        return

    first_paragraph.add_run(f"• {items[0]}")
    for extra in items[1:]:
        p = cell.add_paragraph()
        p.add_run(f"• {extra}")


_LEADING_NUMBER_PREFIX_RE = re.compile(r"^\s*(\d+)(?:\.\d+)*")


def _leading_number(heading: str, default: int = 1) -> int:
    """Pulls the leading top-level number off a heading string (e.g. "4.0
    System Context" -> 4), so a section's X.Y subsection headings can be
    derived from whatever number the caller actually used for the
    section's own Heading 1."""
    match = _LEADING_NUMBER_PREFIX_RE.match(str(heading or ""))
    return int(match.group(1)) if match else default


def apply_iso_table_formatting(table: docx.table.Table, document: docx.Document) -> None:
    """
    Apply a consistent ISO-style formatting to a table:
    - Calibri body style via Normal
    - Light grey header shading
    - Thin borders (via Table Grid style)
    - Content-aware column widths (prose columns wider than short
      categorical/ID columns) instead of an even split, forced via fixed
      table layout so Word doesn't silently re-flow them back to equal
      widths
    - Top-aligned cell text, and a smaller font for wide (6+ column)
      tables so long rows don't wrap into an unreadable wall of narrow
      lines
    - Repeated header row on tables that span a page break
    """
    try:
        # Ensure table style is grid-based
        table.style = "Table Grid"
        table.autofit = False

        n_cols = len(table.columns)
        headers = [c.text for c in table.rows[0].cells] if table.rows else []

        # Header row shading (10% grey) + repeat-on-page-break
        if table.rows:
            hdr_cells = table.rows[0].cells
            for cell in hdr_cells:
                tc = cell._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "D9D9D9")  # light grey
                tcPr.append(shd)
                run = cell.paragraphs[0].runs[0] if cell.paragraphs[0].runs else None
                if run is not None:
                    run.font.bold = True
            _set_repeat_header_row(table.rows[0])

        # Content-aware column widths, sized to the page's actual usable
        # width rather than a hardcoded assumption.
        try:
            section = document.sections[0]
            usable_width = section.page_width - section.left_margin - section.right_margin
        except Exception:
            usable_width = Inches(6.5)

        if n_cols:
            weights = [_column_width_weight(h) for h in headers] if headers else [1.0] * n_cols
            total_weight = sum(weights) or float(n_cols)
            col_widths = [
                Emu(int(usable_width * ((weights[i] if i < len(weights) else 1.0) / total_weight)))
                for i in range(n_cols)
            ]

            for i, col in enumerate(table.columns):
                col.width = col_widths[i]
            for row in table.rows:
                for i, cell in enumerate(row.cells):
                    if i < len(col_widths):
                        cell.width = col_widths[i]

        _force_fixed_table_layout(table)

        # Wide tables get a smaller font so long prose columns wrap onto
        # fewer lines instead of an unreadably narrow column of text.
        font_size = Pt(9) if n_cols >= 6 else Pt(10)

        # Cache the Normal style once
        normal_style = document.styles["Normal"]

        for row in table.rows:
            for cell in row.cells:
                cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                for p in cell.paragraphs:
                    if p.style is None or p.style.name == "Normal":
                        p.style = normal_style
                    for run in p.runs:
                        run.font.size = font_size

    except Exception:
        traceback.print_exc()


def add_iso_page_break(doc: docx.Document) -> None:
    """
    Insert a page break with controlled spacing so we don't accumulate
    random blank lines between sections.
    """
    try:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        doc.add_page_break()
    except Exception:
        traceback.print_exc()


def _add_version_history_table(
    doc: docx.Document,
    version: str,
    author: str,
    description: str = "Initial generated process specification",
) -> None:
    """Add a basic version history table derived from JSON or defaults."""
    try:
        doc.add_heading("Document Control", level=1)

        table = doc.add_table(rows=1, cols=4)
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Version"
        hdr_cells[1].text = "Date"
        hdr_cells[2].text = "Author"
        hdr_cells[3].text = "Description"

        row_cells = table.add_row().cells
        row_cells[0].text = str(version)
        row_cells[1].text = datetime.now().strftime("%Y-%m-%d")
        row_cells[2].text = str(author)
        row_cells[3].text = str(description)

        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()  # spacer
    except Exception:
        traceback.print_exc()


def _enable_auto_update_fields(doc: docx.Document) -> None:
    """
    Sets settings.xml's w:updateFields to true, so Word recalculates every
    field (the TOC inserted by _add_table_of_contents, in particular) the
    moment the document is opened, instead of showing whatever placeholder
    text the field holds until a manual Update Field.
    """
    try:
        settings = doc.settings.element
        if settings.find(qn("w:updateFields")) is not None:
            return
        update_fields = OxmlElement("w:updateFields")
        update_fields.set(qn("w:val"), "true")
        settings.append(update_fields)
    except Exception:
        traceback.print_exc()


def _add_table_of_contents(doc: docx.Document) -> None:
    """
    Insert a Word Table of Contents field. Word recalculates it on open
    (see _enable_auto_update_fields), rather than requiring the reader to
    know to right-click and Update Field manually.
    """
    try:
        _enable_auto_update_fields(doc)

        paragraph = doc.add_paragraph()
        run = paragraph.add_run()

        fld_simple = OxmlElement("w:fldSimple")
        fld_simple.set(
            qn("w:instr"),
            'TOC \\o "1-3" \\h \\z \\u',
        )
        run._r.append(fld_simple)

        inner_run = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.text = "Right-click and select 'Update Field' to generate the Table of Contents."
        inner_run.append(t)
        fld_simple.append(inner_run)
    except Exception:
        traceback.print_exc()
