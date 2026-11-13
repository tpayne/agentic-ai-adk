from process_toolkit.schema.togaf_json import (
    load_master_togaf_json,
    load_togaf_template,
    persist_final_togaf_json,
    validate_togaf_json,
)


def test_load_master_togaf_json_falls_back_to_template_when_no_baseline_exists():
    result = load_master_togaf_json()
    assert result == load_togaf_template()


def test_validate_rejects_missing_document_metadata():
    result = validate_togaf_json({"architecture_vision": {}})
    assert not result["valid"]
    assert any(issue["location"] == "document_metadata" for issue in result["issues"])


def test_validate_rejects_missing_required_metadata_fields():
    result = validate_togaf_json({"document_metadata": {"document_id": "T-1"}})
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "document_metadata.title" in locations
    assert "document_metadata.system_name" in locations


def test_validate_accepts_a_well_formed_document_with_no_requirements():
    doc = {
        "document_metadata": {
            "document_id": "T-1", "system_name": "Checkout", "title": "Checkout Architecture Vision",
            "version": "1.0", "status": "draft",
        },
    }
    result = validate_togaf_json(doc)
    assert result == {"valid": True, "issues": []}


def test_validate_requires_an_id_for_each_requirement():
    doc = {
        "document_metadata": {
            "document_id": "T-1", "system_name": "X", "title": "X Architecture Vision",
            "version": "1.0", "status": "draft",
        },
        "architecture_requirements_specification": {
            "functional_requirements": [{"description": "Create a backup."}],
            "non_functional_requirements": [{"description": "Backups are encrypted."}],
        },
    }

    result = validate_togaf_json(doc)

    assert not result["valid"]
    assert any(
        issue["location"] == "architecture_requirements_specification.functional_requirements[0].id"
        for issue in result["issues"]
    )
    assert any(
        issue["location"] == "architecture_requirements_specification.non_functional_requirements[0].id"
        for issue in result["issues"]
    )


def test_validate_accepts_requirements_with_real_ids():
    doc = {
        "document_metadata": {
            "document_id": "T-1", "system_name": "X", "title": "X Architecture Vision",
            "version": "1.0", "status": "draft",
        },
        "architecture_requirements_specification": {
            "functional_requirements": [{"id": "FR-001", "description": "Create a backup."}],
            "non_functional_requirements": [{"id": "NFR-001", "description": "Backups are encrypted."}],
        },
    }
    result = validate_togaf_json(doc)
    assert result == {"valid": True, "issues": []}


def test_persist_then_load_round_trips():
    doc = {
        "document_metadata": {
            "document_id": "T-1", "system_name": "Checkout", "title": "Checkout Architecture Vision",
            "version": "1.0", "status": "draft",
        },
    }
    result = persist_final_togaf_json(doc)
    assert result.startswith("SUCCESS:")

    loaded = load_master_togaf_json()
    assert loaded["document_metadata"]["title"] == "Checkout Architecture Vision"


def test_persist_rejects_an_invalid_document():
    result = persist_final_togaf_json({"document_metadata": {"document_id": "T-1"}})
    assert result.startswith("ERROR:")


def test_persist_with_no_content_is_a_no_op():
    result = persist_final_togaf_json({})
    assert result.startswith("INFO:")


def test_persist_accepts_a_json_string():
    doc_str = (
        '{"document_metadata": {"document_id": "T-1", "system_name": "Checkout", '
        '"title": "Checkout Architecture Vision", "version": "1.0", "status": "draft"}}'
    )
    result = persist_final_togaf_json(doc_str)
    assert result.startswith("SUCCESS:")


def test_persist_rejects_a_malformed_json_string():
    result = persist_final_togaf_json("{not valid json")
    assert result.startswith("ERROR:")
