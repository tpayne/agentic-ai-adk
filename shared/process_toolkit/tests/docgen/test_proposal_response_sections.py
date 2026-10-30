import docx

from process_toolkit.docgen import proposal_response_sections as prs


def test_executive_summary_always_renders_even_with_no_data():
    doc = docx.Document()
    assert prs._add_executive_summary_section(doc, {}) is True
    assert any(p.text == "1.0 Executive Summary" for p in doc.paragraphs)


def test_executive_summary_uses_the_provided_summary():
    doc = docx.Document()
    assert prs._add_executive_summary_section(doc, {"summary": "A tailored summary."}) is True
    assert any(p.text == "A tailored summary." for p in doc.paragraphs)


def test_understanding_section_is_a_noop_without_data():
    doc = docx.Document()
    assert prs._add_understanding_section(doc, {}) is False


def test_understanding_section_renders_when_present():
    doc = docx.Document()
    assert prs._add_understanding_section(doc, {"our_understanding": "You need X."}) is True
    assert any(p.text == "You need X." for p in doc.paragraphs)


def test_proposed_solution_section_is_a_noop_without_data():
    doc = docx.Document()
    assert prs._add_proposed_solution_section(doc, {}) is False


def test_differentiators_section_renders_bullets():
    doc = docx.Document()
    assert prs._add_differentiators_section(doc, ["Fast delivery.", "24/7 support."]) is True
    bullets = [p.text for p in doc.paragraphs if p.style and p.style.name == "List Bullet"]
    assert bullets == ["Fast delivery.", "24/7 support."]


def test_differentiators_section_is_a_noop_when_empty():
    doc = docx.Document()
    assert prs._add_differentiators_section(doc, None) is False


def test_compliance_matrix_section_sorts_by_requirement_id():
    doc = docx.Document()
    matrix = [
        {"requirement_id": "FR-002", "requirement_text": "b", "response_status": "Fully Compliant", "response": "r2"},
        {"requirement_id": "FR-001", "requirement_text": "a", "response_status": "Partially Compliant", "response": "r1"},
    ]
    assert prs._add_compliance_matrix_section(doc, matrix) is True
    table = doc.tables[0]
    assert table.rows[1].cells[0].text == "FR-001"
    assert table.rows[2].cells[0].text == "FR-002"


def test_compliance_matrix_section_is_a_noop_when_empty():
    doc = docx.Document()
    assert prs._add_compliance_matrix_section(doc, None) is False
    assert doc.tables == []


def test_qualifications_section_is_a_noop_without_data():
    doc = docx.Document()
    assert prs._add_qualifications_section(doc, {}) is False


def test_assumptions_section_renders_bullets():
    doc = docx.Document()
    assert prs._add_assumptions_section(doc, ["Client provides API access."]) is True


def test_risks_and_mitigations_section_renders_a_table():
    doc = docx.Document()
    risks = [{"risk": "Scope creep.", "mitigation": "Change control process."}]
    assert prs._add_risks_and_mitigations_section(doc, risks) is True
    table = doc.tables[0]
    assert table.rows[1].cells[0].text == "• Scope creep."
    assert table.rows[1].cells[1].text == "• Change control process."


def test_pricing_approach_section_is_a_noop_without_data():
    doc = docx.Document()
    assert prs._add_pricing_approach_section(doc, {}) is False


def test_open_questions_section_renders_bullets():
    doc = docx.Document()
    assert prs._add_open_questions_section(doc, ["Which region hosts the data?"]) is True


def test_unaddressed_items_section_includes_the_disclaimer():
    doc = docx.Document()
    assert prs._add_unaddressed_items_section(doc, ["Disaster recovery was flagged as a gap."]) is True
    assert any("inferred or as coverage gaps" in p.text for p in doc.paragraphs)


def test_all_section_renderers_are_noops_on_empty_input():
    doc = docx.Document()
    assert prs._add_understanding_section(doc, {}) is False
    assert prs._add_proposed_solution_section(doc, {}) is False
    assert prs._add_differentiators_section(doc, None) is False
    assert prs._add_compliance_matrix_section(doc, None) is False
    assert prs._add_qualifications_section(doc, {}) is False
    assert prs._add_assumptions_section(doc, None) is False
    assert prs._add_risks_and_mitigations_section(doc, None) is False
    assert prs._add_pricing_approach_section(doc, {}) is False
    assert prs._add_open_questions_section(doc, None) is False
    assert prs._add_unaddressed_items_section(doc, None) is False
    assert doc.tables == []
