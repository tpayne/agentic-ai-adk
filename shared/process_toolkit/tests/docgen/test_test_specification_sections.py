import docx

from process_toolkit.docgen import test_specification_sections as ts


def test_overview_section_always_renders_even_with_no_data():
    doc = docx.Document()
    assert ts._add_test_specification_overview_section(doc, {}) is True
    assert any(p.text == "1.0 Introduction and Purpose" for p in doc.paragraphs)


def test_overview_section_renders_approach_environment_risks_and_open_questions():
    doc = docx.Document()
    data = {
        "summary": "A summary.",
        "test_approach": "Exploratory and scripted testing.",
        "test_environment": "A staging environment mirroring production.",
        "risks": ["Test data may not reflect production volumes."],
        "open_questions": ["Which browsers must be covered?"],
        "source_requirements_used": True,
        "source_design_used": True,
    }
    assert ts._add_test_specification_overview_section(doc, data) is True
    headings = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
    assert headings == [
        "1.1 Test Approach", "1.2 Test Environment", "1.3 Risks", "1.4 Open Questions",
    ]
    assert any("Source Artifacts:" in p.text for p in doc.paragraphs)
    assert any("saved requirements summary" in p.text for p in doc.paragraphs)
    assert any("saved design document" in p.text for p in doc.paragraphs)
    assert not any("cloud architecture diagram" in p.text for p in doc.paragraphs)


def test_overview_section_omits_source_artifacts_line_when_none_used():
    doc = docx.Document()
    assert ts._add_test_specification_overview_section(doc, {}) is True
    assert not any("Source Artifacts:" in p.text for p in doc.paragraphs)


def test_test_cases_register_section_is_a_noop_with_nothing_present():
    doc = docx.Document()
    assert ts._add_test_cases_register_section(doc, {}) is False


def test_test_cases_register_section_splits_by_type():
    doc = docx.Document()
    data = {
        "test_cases": [
            {"id": "TC-001", "type": "functional", "title": "Login", "description": "User can log in.",
             "expected_result": "Session created.", "status": "proposed"},
            {"id": "TC-002", "type": "non_functional", "title": "Latency", "description": "Page loads fast.",
             "expected_result": "Under 2s.", "status": "proposed"},
            {"id": "TC-003", "type": "security", "title": "Auth", "description": "Rejects bad creds.",
             "expected_result": "401 returned.", "status": "proposed"},
        ],
    }
    assert ts._add_test_cases_register_section(doc, data) is True
    headings = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
    assert headings == ["2.1 Functional Tests", "2.2 Non-Functional Tests", "2.3 Security Tests"]
    assert len(doc.tables) == 3


def test_test_cases_table_uses_na_for_a_missing_id():
    doc = docx.Document()
    ts._add_test_cases_table(doc, [{"type": "functional", "description": "x"}])
    table = doc.tables[0]
    assert table.rows[1].cells[0].text == "N/A"


def test_test_cases_table_has_the_expected_columns():
    doc = docx.Document()
    ts._add_test_cases_table(doc, [{"id": "TC-001", "type": "functional", "description": "x"}])
    table = doc.tables[0]
    assert [c.text for c in table.rows[0].cells] == [
        "ID", "Description", "Priority", "Steps", "Expected Result", "Traces To", "Status",
    ]


def test_test_cases_table_defaults_priority_to_medium_when_unset():
    doc = docx.Document()
    ts._add_test_cases_table(doc, [{"id": "TC-001", "type": "functional", "description": "x"}])
    table = doc.tables[0]
    assert table.rows[1].cells[2].text == "Medium"


def test_test_cases_table_includes_steps_and_traces_to():
    doc = docx.Document()
    ts._add_test_cases_table(doc, [{
        "id": "TC-001", "type": "functional", "title": "Login", "description": "User can log in.",
        "steps": ["Open login page", "Enter credentials", "Submit"],
        "expected_result": "Session created.", "traces_to": ["FR-001", "NFR-002"],
        "priority": "high", "status": "proposed",
    }])
    table = doc.tables[0]
    row = table.rows[1]
    assert "Login" in row.cells[1].text
    assert "Open login page" in row.cells[3].text
    assert "Session created." in row.cells[4].text
    assert row.cells[5].text == "FR-001, NFR-002"
    assert row.cells[2].text == "High"
    assert row.cells[6].text == "Proposed"


def test_test_cases_table_folds_preconditions_and_test_data_into_the_description_cell():
    doc = docx.Document()
    ts._add_test_cases_table(doc, [{
        "id": "TC-001", "type": "functional", "description": "User can log in.",
        "preconditions": ["A registered account exists."], "test_data": "user: alice",
    }])
    table = doc.tables[0]
    description_cell_text = table.rows[1].cells[1].text
    assert "A registered account exists." in description_cell_text
    assert "user: alice" in description_cell_text


def test_test_cases_register_section_includes_a_status_key_legend():
    doc = docx.Document()
    data = {"test_cases": [{"id": "TC-001", "type": "functional", "description": "x"}]}
    assert ts._add_test_cases_register_section(doc, data) is True
    assert any("Status key:" in p.text for p in doc.paragraphs)


def test_coverage_summary_section_is_a_noop_with_nothing_present():
    doc = docx.Document()
    assert ts._add_coverage_summary_section(doc, {}) is False
    assert ts._add_coverage_summary_section(doc, {"coverage_summary": {}}) is False


def test_coverage_summary_section_renders_covered_and_not_covered_per_artifact():
    doc = docx.Document()
    data = {
        "coverage_summary": {
            "requirements_covered": ["FR-001"],
            "requirements_not_covered": ["NFR-003"],
            "design_components_covered": ["AuthService"],
            "cloudarch_components_covered": [],
            "cloudarch_components_not_covered": ["LoadBalancer"],
        },
    }
    assert ts._add_coverage_summary_section(doc, data) is True
    headings = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
    assert headings == [
        "3.1 Requirements Coverage", "3.2 Design Coverage", "3.3 Cloud Architecture Coverage",
    ]
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "FR-001" in text
    assert "NFR-003" in text
    assert "AuthService" in text
    assert "LoadBalancer" in text


def test_dependency_register_section_is_a_noop_when_empty():
    doc = docx.Document()
    assert ts._add_test_dependency_register_section(doc, []) is False


def test_dependency_register_section_renders_a_table():
    doc = docx.Document()
    deps = [{"dependency": "Test environment", "description": "A staging env.", "status": "Confirmed"}]
    assert ts._add_test_dependency_register_section(doc, deps) is True
    table = doc.tables[0]
    assert [c.text for c in table.rows[0].cells] == ["Dependency", "Description", "Status"]
    assert table.rows[1].cells[0].text == "Test environment"


def test_glossary_section_is_a_noop_when_empty():
    doc = docx.Document()
    assert ts._add_test_specification_glossary_section(doc, []) is False


def test_glossary_section_renders_a_table_sorted_by_term():
    doc = docx.Document()
    glossary = [
        {"term": "UAT", "definition": "User Acceptance Testing"},
        {"term": "E2E", "definition": "End to End"},
    ]
    assert ts._add_test_specification_glossary_section(doc, glossary) is True
    table = doc.tables[0]
    assert table.rows[1].cells[0].text == "E2E"
    assert table.rows[2].cells[0].text == "UAT"
