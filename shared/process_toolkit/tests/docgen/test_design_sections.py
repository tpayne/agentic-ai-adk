import types

import docx

from process_toolkit.docgen import design_sections


def test_requirements_table_shows_na_for_a_missing_id():
    # Regression test: a requirement record missing "id" (confirmed
    # directly against a real generated design document whose
    # non_functional_requirements were missing it entirely) previously
    # rendered as a BLANK cell in the generated Word document's ID
    # column -- indistinguishable from a rendering bug -- rather than
    # something that's clearly intentional/notable.
    doc = docx.Document()
    design_sections._add_requirements_table(
        doc,
        [{"description": "Backups are encrypted.", "priority": "high", "acceptance_criteria": ["x"]}],
        include_category=False,
    )

    table = doc.tables[0]
    assert table.rows[1].cells[0].text == "N/A"


def test_priority_and_natural_sort_keys():
    assert design_sections._priority_sort_key("high") < design_sections._priority_sort_key("low")
    assert design_sections._natural_sort_key("Requirement 12") == ["requirement ", 12, ""]


def test_bulleted_group_handles_empty_and_values():
    class FakeDoc:
        def __init__(self):
            self.paragraphs = []
            self.runs = []

        def add_paragraph(self, text="", style=None):
            self.paragraphs.append((text, style))

            def add_run(run_text="", **kwargs):
                self.runs.append(run_text)
                return types.SimpleNamespace(bold=None)

            return types.SimpleNamespace(
                paragraph_format=types.SimpleNamespace(
                    left_indent=None, space_before=None, space_after=None
                ),
                add_run=add_run,
            )

    doc = FakeDoc()
    design_sections._add_bulleted_group(doc, "Controls", ["one", "two"], 0.25)
    assert doc.paragraphs
    assert doc.runs[0] == "Controls:"
