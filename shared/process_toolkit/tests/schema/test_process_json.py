from process_toolkit.schema.process_json import (
    load_master_process_json,
    load_process_template,
    persist_final_json,
    validate_process_json,
)


def test_load_master_process_json_falls_back_to_template_when_no_baseline_exists():
    result = load_master_process_json()
    assert result == load_process_template()


def test_validate_rejects_missing_required_fields():
    result = validate_process_json({"process_name": "X"})
    assert not result["valid"]
    assert any("process_steps" in issue["location"] for issue in result["issues"])


def test_validate_rejects_dependency_on_an_unknown_step():
    doc = {
        "process_name": "X",
        "process_steps": [
            {"step_name": "A", "responsible_party": "Ops", "dependencies": ["does-not-exist"]},
        ],
    }
    result = validate_process_json(doc)
    assert not result["valid"]
    assert any("does-not-exist" in issue["issue"] for issue in result["issues"])


def test_validate_accepts_a_well_formed_document():
    doc = {
        "process_name": "Onboarding",
        "process_steps": [
            {"step_name": "A", "responsible_party": "Ops", "dependencies": []},
            {"step_name": "B", "responsible_party": "Finance", "dependencies": ["A"]},
        ],
    }
    result = validate_process_json(doc)
    assert result == {"valid": True, "issues": []}


def test_persist_then_load_round_trips():
    doc = {
        "process_name": "Onboarding",
        "process_steps": [{"step_name": "A", "responsible_party": "Ops", "dependencies": []}],
    }
    result = persist_final_json(doc)
    assert result.startswith("SUCCESS:")

    loaded = load_master_process_json()
    assert loaded["process_name"] == "Onboarding"


def test_persist_rejects_an_invalid_document():
    result = persist_final_json({"process_name": "X"})
    assert result.startswith("ERROR:")


def test_validate_rejects_metrics_csf_cff_reporting_entries_missing_a_description():
    # A real live run produced bare {"id", "metric"} objects with no
    # "description" for these four fields, leaving sections 5-8 of the
    # generated document with a blank Description column. This is now a
    # hard validation gate so Design_Agent can't persist that shape.
    doc = {
        "process_name": "X",
        "process_steps": [{"step_name": "A", "responsible_party": "Ops", "dependencies": []}],
        "metrics": [{"id": "M-001", "metric": "Deployment Frequency"}],
        "critical_success_factors": [{"id": "CSF-001", "factor": "Automation"}],
        "critical_failure_factors": [{"id": "CFF-001", "factor": "Manual changes"}],
        "reporting_and_analytics": [{"id": "REP-001", "report": "Dashboard"}],
    }
    result = validate_process_json(doc)
    assert not result["valid"]
    for field in ("metrics", "critical_success_factors", "critical_failure_factors", "reporting_and_analytics"):
        assert any(
            issue["location"] == f"{field}[0].description" for issue in result["issues"]
        ), f"expected a missing-description issue for {field}"


def test_validate_accepts_metrics_csf_cff_reporting_entries_with_a_description():
    doc = {
        "process_name": "X",
        "process_steps": [{"step_name": "A", "responsible_party": "Ops", "dependencies": []}],
        "metrics": [{"id": "M-001", "metric": "Deployment Frequency", "description": "How often we ship."}],
        "critical_success_factors": [{"id": "CSF-001", "factor": "Automation", "description": "Reduces errors."}],
        "critical_failure_factors": [{"id": "CFF-001", "factor": "Manual changes", "description": "Causes drift."}],
        "reporting_and_analytics": [{"id": "REP-001", "report": "Dashboard", "description": "Shows status."}],
    }
    result = validate_process_json(doc)
    assert result == {"valid": True, "issues": []}
