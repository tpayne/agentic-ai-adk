# process_agents/helpers/doc_structure.py

import docx
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import traceback
import logging

logger = logging.getLogger("ProcessArchitect.DocStructure")

def _add_header(doc, label):
    """Adds a bold section sub-header with standard spacing."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(0)
    p.add_run(label).bold = True
    return p

def _add_bullet(doc, text):
    """Adds a standard bullet point with tight spacing."""
    b = doc.add_paragraph(str(text), style="List Bullet")
    b.paragraph_format.space_before = Pt(0)
    b.paragraph_format.space_after = Pt(0)
    return b

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
