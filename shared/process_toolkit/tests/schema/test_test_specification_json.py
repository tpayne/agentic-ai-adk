from process_toolkit.schema.test_specification_json import (
    TEST_SPECIFICATION_FILENAME,
    load_test_specification_template,
    validate_test_specification,
)


def test_test_specification_filename_matches_the_real_persistence_module():
    from process_toolkit.test_specification.test_specification import (
        TEST_SPECIFICATION_FILENAME as CANONICAL_FILENAME,
    )

    assert TEST_SPECIFICATION_FILENAME == CANONICAL_FILENAME


def test_load_test_specification_template_is_a_fresh_copy_each_time():
    a = load_test_specification_template()
    b = load_test_specification_template()
    assert a == b
    a["summary"] = "mutated"
    assert b["summary"] == ""


def test_validate_rejects_non_dict_input():
    result = validate_test_specification("not a dict")
    assert not result["valid"]
    assert result["issues"][0]["location"] == "$"


def test_validate_requires_a_test_cases_list():
    result = validate_test_specification({})
    assert not result["valid"]
    assert result["issues"][0]["location"] == "test_cases"


def test_validate_accepts_a_well_formed_specification():
    doc = {
        "test_cases": [
            {
                "id": "TC-001", "type": "functional", "description": "Validates login.",
                "expected_result": "User is logged in.", "source_artifact": "requirements",
            },
        ],
    }
    result = validate_test_specification(doc)
    assert result == {"valid": True, "issues": []}


def test_validate_requires_an_id_for_each_test_case():
    doc = {"test_cases": [{"type": "functional", "description": "A", "expected_result": "B"}]}
    result = validate_test_specification(doc)
    assert not result["valid"]
    assert any(issue["location"] == "test_cases[0].id" for issue in result["issues"])


def test_validate_rejects_duplicate_ids():
    doc = {
        "test_cases": [
            {"id": "TC-001", "type": "functional", "description": "A", "expected_result": "X"},
            {"id": "TC-001", "type": "functional", "description": "B", "expected_result": "Y"},
        ],
    }
    result = validate_test_specification(doc)
    assert not result["valid"]
    assert any("Duplicate id" in issue["issue"] for issue in result["issues"])


def test_validate_rejects_an_unknown_type():
    doc = {"test_cases": [{"id": "TC-001", "type": "weird", "description": "A", "expected_result": "X"}]}
    result = validate_test_specification(doc)
    assert not result["valid"]
    assert any(issue["location"] == "test_cases[0].type" for issue in result["issues"])


def test_validate_requires_a_description():
    doc = {"test_cases": [{"id": "TC-001", "type": "functional", "expected_result": "X"}]}
    result = validate_test_specification(doc)
    assert not result["valid"]
    assert any(issue["location"] == "test_cases[0].description" for issue in result["issues"])


def test_validate_requires_an_expected_result():
    doc = {"test_cases": [{"id": "TC-001", "type": "functional", "description": "A"}]}
    result = validate_test_specification(doc)
    assert not result["valid"]
    assert any(issue["location"] == "test_cases[0].expected_result" for issue in result["issues"])


def test_validate_rejects_an_unknown_source_artifact():
    doc = {"test_cases": [{
        "id": "TC-001", "type": "functional", "description": "A", "expected_result": "X",
        "source_artifact": "somewhere_else",
    }]}
    result = validate_test_specification(doc)
    assert not result["valid"]
    assert any(issue["location"] == "test_cases[0].source_artifact" for issue in result["issues"])
