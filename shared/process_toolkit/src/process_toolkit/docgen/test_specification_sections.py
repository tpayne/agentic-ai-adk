"""Bespoke renderers for the test-specification document: Introduction and
Purpose (with Risks/Open Questions as subsections), the Test Cases
Register (split by type into Functional/Non-Functional/Security/
Performance/Integration/Usability/Compliance/Infrastructure tables, each
row carrying its own steps/expected result/traceability), Coverage
Summary (which requirements/design components/cloud architecture
components have at least one tracing test case, and which don't),
Dependency Register, and Glossary -- rendered directly from
test_specification.json's own fields (see
process_toolkit.test_specification.test_specification and
process_toolkit.schema.test_specification_json for that shape).

Follows requirements_sections.py's own conventions exactly: a short
opening paragraph, a fixed set of columns, natural-id sort, apply_iso_
table_formatting/_set_cell_bullets, True/False no-op-render return.
"""

import traceback

import docx

from process_toolkit.docgen.structure import apply_iso_table_formatting, _set_cell_bullets, _leading_number
from process_toolkit.docgen.design_sections import _natural_sort_key, _priority_sort_key
from process_toolkit.docgen.requirements_sections import (
    _coerce_to_text, _add_bullet_list_subsection, _add_key_legend, _add_prose_subsection, _set_header_row,
)


# ============================================================
# 1.0 INTRODUCTION AND PURPOSE
# ============================================================

def _add_test_specification_overview_section(
    doc: docx.Document, data: dict, heading: str = "1.0 Introduction and Purpose",
) -> bool:
    """1.0 Introduction and Purpose -- summary prose, test approach, test
    environment, which source artifacts were actually used, with Risks/
    Open Questions as numbered subsections -- mirrors requirements_
    sections.py's own _add_requirements_overview_section shape. Always
    renders -- this is the document's own opening section."""
    try:
        doc.add_heading(heading, level=1)
        lead = _leading_number(heading, default=1)

        summary = data.get("summary")
        doc.add_paragraph(
            str(summary) if summary else
            "This document records the test cases that validate the requirements, design, and/or "
            "cloud architecture this effort has produced, their traceability back to those source "
            "artifacts, and any coverage gaps identified."
        )

        _add_prose_subsection(doc, data.get("test_approach"), f"{lead}.1 Test Approach", level=2)
        _add_prose_subsection(doc, data.get("test_environment"), f"{lead}.2 Test Environment", level=2)

        sources_used = []
        if data.get("source_requirements_used"):
            sources_used.append("the saved requirements summary")
        if data.get("source_design_used"):
            sources_used.append("the saved design document")
        if data.get("source_cloudarch_used"):
            sources_used.append("the saved cloud architecture diagram")
        if sources_used:
            p = doc.add_paragraph()
            p.add_run("Source Artifacts: ").bold = True
            p.add_run(", ".join(sources_used))

        subsection = 3
        for key, label in (("risks", "Risks"), ("open_questions", "Open Questions")):
            values = [_coerce_to_text(v) for v in (data.get(key) or []) if v not in (None, "", {}, [])]
            values = [v for v in values if v]
            if not values:
                continue
            doc.add_heading(f"{lead}.{subsection} {label}", level=2)
            subsection += 1
            for v in values:
                doc.add_paragraph(v, style="List Bullet")

        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 2.0 TEST CASES REGISTER
# ============================================================

_TYPE_SECTIONS = (
    ("functional", "Functional Tests"),
    ("non_functional", "Non-Functional Tests"),
    ("security", "Security Tests"),
    ("performance", "Performance Tests"),
    ("integration", "Integration Tests"),
    ("usability", "Usability Tests"),
    ("compliance", "Compliance Tests"),
    ("infrastructure", "Infrastructure Tests"),
)


def _add_test_cases_table(doc: docx.Document, items) -> None:
    """One row per test case: ID, a Description cell combining title/
    description/preconditions/test data (so the main table stays a
    manageable width), Priority, Steps, Expected Result, Traces To,
    Status. Priority defaults to "medium" when genuinely unset, same
    mandatory-column convention requirements_sections.py's own register
    table uses, for the same reason (a sensible default beats a column
    the agent simply never populated)."""
    items = sorted(items, key=lambda r: _natural_sort_key(r.get("id")))

    headers = ["ID", "Description", "Priority", "Steps", "Expected Result", "Traces To", "Status"]
    table = doc.add_table(rows=1, cols=len(headers))
    _set_header_row(table, headers)

    for item in items:
        row = table.add_row().cells
        row[0].text = str(item.get("id") or "N/A")

        description_parts = [item.get("title"), item.get("description")]
        description_text = "\n".join(str(p) for p in description_parts if p)
        preconditions = [str(p) for p in (item.get("preconditions") or []) if p]
        if preconditions:
            description_text += "\nPreconditions: " + "; ".join(preconditions)
        test_data = item.get("test_data")
        if test_data:
            description_text += f"\nTest Data: {test_data}"
        _set_cell_bullets(row[1], description_text)

        priority = item.get("priority") or "medium"
        row[2].text = str(priority).title()
        _set_cell_bullets(row[3], item.get("steps"))
        _set_cell_bullets(row[4], item.get("expected_result"))
        traces_to = [str(t) for t in (item.get("traces_to") or [])]
        row[5].text = ", ".join(traces_to)
        row[6].text = str(item.get("status") or "").replace("_", " ").title()

    apply_iso_table_formatting(table, doc)
    doc.add_paragraph()


def _add_test_cases_register_section(
    doc: docx.Document, data: dict, heading: str = "2.0 Test Cases Register",
) -> bool:
    """2.0 Test Cases Register -- splits test cases by type into
    Functional/Non-Functional/Security/Performance/Integration/
    Usability/Compliance/Infrastructure tables, sorted by id."""
    try:
        lead = _leading_number(heading, default=2)

        test_cases = [t for t in (data.get("test_cases") or []) if isinstance(t, dict)]
        if not test_cases:
            return False

        by_type: dict = {}
        for item in test_cases:
            by_type.setdefault(item.get("type"), []).append(item)

        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section lists the test cases that validate the requirements, design, and/or "
            "cloud architecture this effort has produced, grouped by test type. Each table is "
            "ordered by identifier."
        )
        _add_key_legend(doc, "Status key", (
            ("Proposed", "not yet executed"),
            ("Automated", "implemented as an automated check"),
            ("Passed", "executed and met its expected result"),
            ("Failed", "executed and did not meet its expected result"),
            ("Blocked", "cannot currently be executed"),
        ))

        subsection = 1
        for test_type, label in _TYPE_SECTIONS:
            items = by_type.get(test_type) or []
            if not items:
                continue
            doc.add_heading(f"{lead}.{subsection} {label}", level=2)
            subsection += 1
            _add_test_cases_table(doc, items)

        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 3.0 COVERAGE SUMMARY
# ============================================================

def _add_coverage_table(doc: docx.Document, covered, not_covered) -> None:
    """One row per id/name, sorted naturally, with its own Status column
    ("Covered"/"Not Covered") -- same one-row-per-item table convention
    every other register in this document uses, replacing the earlier
    bold-label/comma-separated-paragraph rendering (hard to scan once a
    list runs long)."""
    headers = ["Status", "ID / Component"]
    table = doc.add_table(rows=1, cols=len(headers))
    _set_header_row(table, headers)

    for item in sorted(covered, key=_natural_sort_key):
        row = table.add_row().cells
        row[0].text = "Covered"
        row[1].text = str(item)
    for item in sorted(not_covered, key=_natural_sort_key):
        row = table.add_row().cells
        row[0].text = "Not Covered"
        row[1].text = str(item)

    apply_iso_table_formatting(table, doc)
    doc.add_paragraph()


def _add_coverage_summary_section(
    doc: docx.Document, data: dict, heading: str = "3.0 Coverage Summary",
) -> bool:
    """3.0 Coverage Summary -- for each source artifact that was actually
    used, which of its requirements/components have at least one tracing
    test case, and which don't, as a Status/ID table. A no-op container
    when "coverage_summary" is absent or every one of its six lists is
    empty."""
    try:
        coverage = data.get("coverage_summary")
        if not isinstance(coverage, dict) or not any(coverage.get(k) for k in (
            "requirements_covered", "requirements_not_covered",
            "design_components_covered", "design_components_not_covered",
            "cloudarch_components_covered", "cloudarch_components_not_covered",
        )):
            return False

        lead = _leading_number(heading, default=3)
        doc.add_heading(heading, level=1)
        doc.add_paragraph(
            "This section records, for each source artifact used, which of its requirements or "
            "components have at least one tracing test case, and which currently have none."
        )

        subsection = 1
        for covered_key, not_covered_key, label in (
            ("requirements_covered", "requirements_not_covered", "Requirements Coverage"),
            ("design_components_covered", "design_components_not_covered", "Design Coverage"),
            ("cloudarch_components_covered", "cloudarch_components_not_covered", "Cloud Architecture Coverage"),
        ):
            covered = [str(c) for c in (coverage.get(covered_key) or [])]
            not_covered = [str(c) for c in (coverage.get(not_covered_key) or [])]
            if not covered and not not_covered:
                continue
            doc.add_heading(f"{lead}.{subsection} {label}", level=2)
            subsection += 1
            _add_coverage_table(doc, covered, not_covered)

        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 4.0 DEPENDENCY REGISTER
# ============================================================

def _add_test_dependency_register_section(
    doc: docx.Document, dependencies, heading: str = "4.0 Dependency Register",
) -> bool:
    """4.0 Dependency Register -- external dependencies this test effort
    relies on (a test environment, a data provider, a third-party
    service), mirrors requirements_sections.py's own dependency register
    exactly."""
    try:
        items = [d for d in (dependencies or []) if isinstance(d, dict)]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph("This section records external dependencies this test effort relies on.")
        _add_key_legend(doc, "Status key", (
            ("Confirmed", "verified to be available/in place"),
            ("Unconfirmed", "assumed, not yet verified"),
            ("At Risk", "verification raised a concern"),
        ))

        headers = ["Dependency", "Description", "Status"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for d in items:
            row = table.add_row().cells
            row[0].text = str(d.get("dependency") or "")
            _set_cell_bullets(row[1], d.get("description"))
            row[2].text = str(d.get("status") or "")
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True
    except Exception:
        traceback.print_exc()
        return False


# ============================================================
# 5.0 GLOSSARY
# ============================================================

def _add_test_specification_glossary_section(
    doc: docx.Document, glossary, heading: str = "5.0 Glossary",
) -> bool:
    """5.0 Glossary -- mirrors requirements_sections.py's own glossary
    section exactly."""
    try:
        items = [g for g in (glossary or []) if isinstance(g, dict) and g.get("term")]
        if not items:
            return False

        doc.add_heading(heading, level=1)
        doc.add_paragraph("This section defines acronyms and terms used elsewhere in this document.")

        items = sorted(items, key=lambda g: str(g.get("term") or "").lower())

        headers = ["Term", "Definition"]
        table = doc.add_table(rows=1, cols=len(headers))
        _set_header_row(table, headers)
        for g in items:
            row = table.add_row().cells
            row[0].text = str(g.get("term") or "")
            _set_cell_bullets(row[1], g.get("definition"))
        apply_iso_table_formatting(table, doc)
        doc.add_paragraph()
        return True
    except Exception:
        traceback.print_exc()
        return False
