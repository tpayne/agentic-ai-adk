from process_toolkit.schema.requirements_json import (
    REQUIREMENTS_SUMMARY_FILENAME,
    is_old_format_requirements_summary,
    load_requirements_summary_template,
    validate_requirements_summary,
)


def test_requirements_summary_filename_matches_the_real_persistence_module():
    # Guards against drift between this module's own re-export and the
    # real filename requirements_summary.py actually saves/loads.
    from process_toolkit.requirements_summary.requirements_summary import (
        REQUIREMENTS_SUMMARY_FILENAME as CANONICAL_FILENAME,
    )

    assert REQUIREMENTS_SUMMARY_FILENAME == CANONICAL_FILENAME


def test_load_requirements_summary_template_is_a_fresh_copy_each_time():
    a = load_requirements_summary_template()
    b = load_requirements_summary_template()
    assert a == b
    a["summary"] = "mutated"
    assert b["summary"] == ""


def test_validate_rejects_non_dict_input():
    result = validate_requirements_summary("not a dict")
    assert not result["valid"]
    assert result["issues"][0]["location"] == "$"


def test_validate_accepts_a_well_formed_summary():
    doc = {
        "requirements_register": [
            {"id": "FR-001", "type": "functional", "description": "Allow login.", "source": "a.txt",
             "acceptance_criteria": ["A user can log in."], "status": "proposed"},
        ],
    }
    result = validate_requirements_summary(doc)
    assert result == {"valid": True, "issues": []}


def test_validate_requires_an_id_for_each_requirement():
    doc = {"requirements_register": [{"type": "functional", "description": "Allow login."}]}
    result = validate_requirements_summary(doc)
    assert not result["valid"]
    assert any(issue["location"] == "requirements_register[0].id" for issue in result["issues"])


def test_validate_rejects_duplicate_ids():
    doc = {
        "requirements_register": [
            {"id": "FR-001", "type": "functional", "description": "A"},
            {"id": "FR-001", "type": "functional", "description": "B"},
        ],
    }
    result = validate_requirements_summary(doc)
    assert not result["valid"]
    assert any("Duplicate id" in issue["issue"] for issue in result["issues"])


def test_validate_rejects_an_unknown_type():
    doc = {"requirements_register": [{"id": "FR-001", "type": "weird", "description": "A"}]}
    result = validate_requirements_summary(doc)
    assert not result["valid"]
    assert any(issue["location"] == "requirements_register[0].type" for issue in result["issues"])


def test_validate_requires_a_description():
    doc = {"requirements_register": [{"id": "FR-001", "type": "functional"}]}
    result = validate_requirements_summary(doc)
    assert not result["valid"]
    assert any(issue["location"] == "requirements_register[0].description" for issue in result["issues"])


def test_validate_flags_a_dangling_priority_reference():
    doc = {
        "requirements_register": [{"id": "FR-001", "type": "functional", "description": "A"}],
        "requirement_priorities": [{"requirement_id": "FR-999", "priority": "high"}],
    }
    result = validate_requirements_summary(doc)
    assert not result["valid"]
    assert any(
        issue["location"] == "requirement_priorities[0].requirement_id" for issue in result["issues"]
    )


def test_validate_flags_a_dangling_conflict_reference():
    doc = {
        "requirements_register": [{"id": "FR-001", "type": "functional", "description": "A"}],
        "conflicting_requirements": [{"requirement_ids": ["FR-001", "FR-999"]}],
    }
    result = validate_requirements_summary(doc)
    assert not result["valid"]
    assert any(
        issue["location"] == "conflicting_requirements[0].requirement_ids" for issue in result["issues"]
    )


def test_is_old_format_detects_the_legacy_flat_shape():
    assert is_old_format_requirements_summary({"functional_requirements": ["Allow login."]})
    assert is_old_format_requirements_summary({"goals_or_objectives": ["Grow revenue."]})


def test_is_old_format_is_false_when_a_real_register_is_present():
    assert not is_old_format_requirements_summary({
        "requirements_register": [{"id": "FR-001", "type": "functional", "description": "A"}],
        "functional_requirements": ["Allow login."],  # stray leftover key, register still wins
    })


def test_is_old_format_is_false_for_a_non_dict_or_empty_register():
    assert not is_old_format_requirements_summary("not a dict")
    assert not is_old_format_requirements_summary({"requirements_register": []})


def test_validate_treats_old_format_as_valid_with_nothing_to_check():
    doc = {"functional_requirements": ["Allow login."], "non_functional_requirements": []}
    result = validate_requirements_summary(doc)
    assert result == {"valid": True, "issues": []}
