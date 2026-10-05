from coded_tools.common.design_json import (
    load_design_template,
    load_master_design_json,
    persist_final_design_json,
    validate_design_json,
)


def test_load_master_design_json_falls_back_to_template_when_no_baseline_exists():
    result = load_master_design_json()
    assert result == load_design_template()


def test_validate_rejects_missing_document_metadata():
    result = validate_design_json({"high_level_design": {}})
    assert not result["valid"]
    assert any(issue["location"] == "document_metadata" for issue in result["issues"])


def test_validate_rejects_missing_required_metadata_fields():
    result = validate_design_json({"document_metadata": {"document_id": "D-1"}})
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "document_metadata.document_type" in locations
    assert "document_metadata.title" in locations


def test_validate_rejects_unknown_document_type():
    doc = {
        "document_metadata": {
            "document_id": "D-1", "document_type": "WeirdType", "system_name": "X",
            "title": "X Design", "version": "1.0", "status": "draft",
        },
    }
    result = validate_design_json(doc)
    assert not result["valid"]
    assert any("document_type" in issue["location"] for issue in result["issues"])


def test_validate_requires_high_level_design_for_hld_document_type():
    doc = {
        "document_metadata": {
            "document_id": "D-1", "document_type": "HLD", "system_name": "X",
            "title": "X Design", "version": "1.0", "status": "draft",
        },
    }
    result = validate_design_json(doc)
    assert not result["valid"]
    assert any(issue["location"] == "high_level_design" for issue in result["issues"])


def test_validate_requires_both_sections_for_combined_document_type():
    doc = {
        "document_metadata": {
            "document_id": "D-1", "document_type": "Combined", "system_name": "X",
            "title": "X Design", "version": "1.0", "status": "draft",
        },
        "high_level_design": {},
    }
    result = validate_design_json(doc)
    assert not result["valid"]
    assert any(issue["location"] == "low_level_design" for issue in result["issues"])


def test_validate_accepts_a_well_formed_hld_document():
    doc = {
        "document_metadata": {
            "document_id": "D-1", "document_type": "HLD", "system_name": "Checkout",
            "title": "Checkout HLD", "version": "1.0", "status": "draft",
        },
        "high_level_design": {"components": []},
    }
    result = validate_design_json(doc)
    assert result == {"valid": True, "issues": []}


def test_persist_then_load_round_trips():
    doc = {
        "document_metadata": {
            "document_id": "D-1", "document_type": "HLD", "system_name": "Checkout",
            "title": "Checkout HLD", "version": "1.0", "status": "draft",
        },
        "high_level_design": {"components": []},
    }
    result = persist_final_design_json(doc)
    assert result.startswith("SUCCESS:")

    loaded = load_master_design_json()
    assert loaded["document_metadata"]["title"] == "Checkout HLD"


def test_persist_rejects_an_invalid_document():
    result = persist_final_design_json({"document_metadata": {"document_id": "D-1"}})
    assert result.startswith("ERROR:")
