from process_toolkit.schema.itsm_json import (
    load_itsm_template,
    load_master_itsm_json,
    persist_final_itsm_json,
    validate_itsm_json,
)


def _valid_metadata():
    return {
        "document_id": "I-1", "system_name": "Checkout", "title": "Checkout ITSM Process Document",
        "version": "1.0", "status": "draft",
    }


def test_load_master_itsm_json_falls_back_to_template_when_no_baseline_exists():
    result = load_master_itsm_json()
    assert result == load_itsm_template()


def test_validate_rejects_missing_document_metadata():
    result = validate_itsm_json({"service_catalog": {}})
    assert not result["valid"]
    assert any(issue["location"] == "document_metadata" for issue in result["issues"])


def test_validate_rejects_missing_required_metadata_fields():
    result = validate_itsm_json({"document_metadata": {"document_id": "I-1"}})
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "document_metadata.title" in locations
    assert "document_metadata.system_name" in locations


def test_validate_accepts_a_well_formed_document_with_no_other_sections():
    doc = {"document_metadata": _valid_metadata()}
    result = validate_itsm_json(doc)
    assert result == {"valid": True, "issues": []}


def test_validate_requires_id_and_name_for_each_service():
    doc = {
        "document_metadata": _valid_metadata(),
        "service_catalog": {"services": [{"description": "No id or name."}]},
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "service_catalog.services[0].id" in locations
    assert "service_catalog.services[0].name" in locations


def test_validate_rejects_a_non_object_item_in_services():
    # Regression guard, same shape as togaf_json.py's own capabilities check --
    # a bare int in a list that should contain objects must be flagged, not
    # silently skipped (it previously crashed downstream docgen code).
    doc = {
        "document_metadata": _valid_metadata(),
        "service_catalog": {"services": [42, {"id": "SVC-001", "name": "Email"}]},
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    assert any(issue["location"] == "service_catalog.services[0]" for issue in result["issues"])


def test_validate_requires_priority_impact_and_urgency_for_each_priority_matrix_entry():
    doc = {
        "document_metadata": _valid_metadata(),
        "incident_management": {"priority_matrix": [{"target_response_time": "15 minutes"}]},
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "incident_management.priority_matrix[0].priority" in locations
    assert "incident_management.priority_matrix[0].impact" in locations
    assert "incident_management.priority_matrix[0].urgency" in locations


def test_validate_requires_step_id_and_step_name_for_each_process_step():
    # Exercises all four domains that reuse _validate_process_steps.
    doc = {
        "document_metadata": _valid_metadata(),
        "incident_management": {"process_steps": [{"description": "Missing step_id/step_name."}]},
        "problem_management": {"process_steps": [{"description": "Missing step_id/step_name."}]},
        "change_management": {"process_steps": [{"description": "Missing step_id/step_name."}]},
        "request_fulfillment": {"process_steps": [{"description": "Missing step_id/step_name."}]},
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    for domain in ("incident_management", "problem_management", "change_management", "request_fulfillment"):
        assert f"{domain}.process_steps[0].step_id" in locations
        assert f"{domain}.process_steps[0].step_name" in locations


def test_validate_accepts_well_formed_process_steps():
    doc = {
        "document_metadata": _valid_metadata(),
        "incident_management": {
            "process_steps": [{"step_id": "INC-1", "step_name": "Log Incident"}],
        },
    }
    result = validate_itsm_json(doc)
    assert result == {"valid": True, "issues": []}


def test_validate_requires_type_and_approval_path_for_each_change_type():
    doc = {
        "document_metadata": _valid_metadata(),
        "change_management": {"change_types": [{"description": "Missing type/approval_path."}]},
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "change_management.change_types[0].type" in locations
    assert "change_management.change_types[0].approval_path" in locations


def test_validate_requires_id_metric_and_target_for_each_sla():
    doc = {
        "document_metadata": _valid_metadata(),
        "service_level_management": {"slas": [{"service_id": "SVC-001"}]},
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "service_level_management.slas[0].id" in locations
    assert "service_level_management.slas[0].metric" in locations
    assert "service_level_management.slas[0].target" in locations


def test_validate_requires_id_and_name_for_each_configuration_item():
    doc = {
        "document_metadata": _valid_metadata(),
        "configuration_management": {"configuration_items": [{"type": "Server"}]},
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "configuration_management.configuration_items[0].id" in locations
    assert "configuration_management.configuration_items[0].name" in locations


def test_validate_requires_source_and_target_ci_for_each_relationship():
    doc = {
        "document_metadata": _valid_metadata(),
        "configuration_management": {"relationships": [{"relationship_type": "depends_on"}]},
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "configuration_management.relationships[0].source_ci" in locations
    assert "configuration_management.relationships[0].target_ci" in locations


def test_validate_requires_process_area_and_activity_for_each_raci_entry():
    doc = {
        "document_metadata": _valid_metadata(),
        "raci_matrix": [{"responsible": "Service Desk"}],
    }
    result = validate_itsm_json(doc)
    assert not result["valid"]
    locations = {issue["location"] for issue in result["issues"]}
    assert "raci_matrix[0].process_area" in locations
    assert "raci_matrix[0].activity" in locations


def test_validate_accepts_a_well_formed_raci_entry():
    doc = {
        "document_metadata": _valid_metadata(),
        "raci_matrix": [{
            "process_area": "Incident Management", "activity": "Log Incident",
            "responsible": "Service Desk", "accountable": "Incident Manager",
            "consulted": "", "informed": "Customer",
        }],
    }
    result = validate_itsm_json(doc)
    assert result == {"valid": True, "issues": []}


def test_validate_leaves_sections_that_are_not_yet_filled_in_unflagged():
    # Mid-generation documents legitimately have sections the agent hasn't
    # populated yet -- a section that's absent, or present but not a list
    # where a list is expected, must not itself be an issue.
    doc = {
        "document_metadata": _valid_metadata(),
        "change_management": {},
        "configuration_management": {"configuration_items": "not a list yet"},
    }
    result = validate_itsm_json(doc)
    assert result == {"valid": True, "issues": []}


def test_persist_then_load_round_trips():
    doc = {"document_metadata": _valid_metadata()}
    result = persist_final_itsm_json(doc)
    assert result.startswith("SUCCESS:")

    loaded = load_master_itsm_json()
    assert loaded["document_metadata"]["title"] == "Checkout ITSM Process Document"


def test_persist_rejects_an_invalid_document():
    result = persist_final_itsm_json({"document_metadata": {"document_id": "I-1"}})
    assert result.startswith("ERROR:")


def test_persist_with_no_content_is_a_no_op():
    result = persist_final_itsm_json({})
    assert result.startswith("INFO:")


def test_persist_accepts_a_json_string():
    doc_str = (
        '{"document_metadata": {"document_id": "I-1", "system_name": "Checkout", '
        '"title": "Checkout ITSM Process Document", "version": "1.0", "status": "draft"}}'
    )
    result = persist_final_itsm_json(doc_str)
    assert result.startswith("SUCCESS:")


def test_persist_rejects_a_malformed_json_string():
    result = persist_final_itsm_json("{not valid json")
    assert result.startswith("ERROR:")
