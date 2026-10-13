from process_toolkit.schema.process_json import (
    load_master_process_json,
    load_process_template,
    persist_final_json,
    validate_process_json,
)

_LONG_DESCRIPTION = (
    "This step covers the full set of activities a delivery team performs here, including what "
    "triggers it, how the work gets done, and what artifacts it produces for the next step."
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
            {"step_name": "A", "responsible_party": "Ops", "description": _LONG_DESCRIPTION, "dependencies": ["does-not-exist"]},
        ],
    }
    result = validate_process_json(doc)
    assert not result["valid"]
    assert any("does-not-exist" in issue["issue"] for issue in result["issues"])


def test_validate_rejects_a_process_step_missing_a_description():
    # A real live run produced process_steps with only step_name/responsible_
    # party/dependencies populated, leaving the rendered document's "3.x"
    # sections with no description/purpose/scope/etc. at all -- traced to
    # PROCESS_TEMPLATE's process_steps entry being a bare [] instead of a
    # one-item structural hint like every other field has, so Design_Agent
    # had nothing to normalize against. This is now a hard validation gate.
    doc = {
        "process_name": "X",
        "process_steps": [{"step_name": "A", "responsible_party": "Ops", "dependencies": []}],
    }
    result = validate_process_json(doc)
    assert not result["valid"]
    assert any(issue["location"] == "process_steps[0].description" for issue in result["issues"])


def test_validate_rejects_a_process_step_description_that_is_too_thin():
    # A real live run produced full-schema process_steps (every field
    # present, satisfying the "missing required field" gate above) where
    # description/purpose/introduction/scope were each a single short
    # clause (e.g. "Teams execute iterations synchronized by Scrum of
    # Scrums...", ~115 chars) -- technically valid by presence alone, but
    # the rendered document read like a summary, not a process doc.
    doc = {
        "process_name": "X",
        "process_steps": [{
            "step_name": "A", "responsible_party": "Ops", "description": "A short clause.", "dependencies": [],
        }],
    }
    result = validate_process_json(doc)
    assert not result["valid"]
    assert any(issue["location"] == "process_steps[0].description" for issue in result["issues"])


def test_validate_rejects_a_non_string_description_without_raising():
    # Regression test: a malformed description that isn't a string (e.g. a
    # model emitting a number or list instead of text) must come back as a
    # validation issue, not raise TypeError out of len(description).
    doc = {
        "process_name": "X",
        "process_steps": [{
            "step_name": "A", "responsible_party": "Ops", "description": 12345, "dependencies": [],
        }],
    }
    result = validate_process_json(doc)
    assert not result["valid"]
    assert any(issue["location"] == "process_steps[0].description" for issue in result["issues"])


def test_validate_rejects_a_too_thin_purpose_introduction_or_scope():
    doc = {
        "process_name": "X",
        "process_steps": [],
        "purpose": "Too short.",
        "introduction": "Too short.",
        "scope": "Too short.",
    }
    result = validate_process_json(doc)
    assert not result["valid"]
    for field in ("purpose", "introduction", "scope"):
        assert any(issue["location"] == field for issue in result["issues"]), f"expected a thin-{field} issue"


def test_validate_accepts_a_well_formed_document():
    doc = {
        "process_name": "Onboarding",
        "process_steps": [
            {"step_name": "A", "responsible_party": "Ops", "description": _LONG_DESCRIPTION, "dependencies": []},
            {"step_name": "B", "responsible_party": "Finance", "description": _LONG_DESCRIPTION, "dependencies": ["A"]},
        ],
    }
    result = validate_process_json(doc)
    assert result == {"valid": True, "issues": []}


def test_persist_then_load_round_trips():
    doc = {
        "process_name": "Onboarding",
        "process_steps": [{"step_name": "A", "responsible_party": "Ops", "description": _LONG_DESCRIPTION, "dependencies": []}],
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
        "process_steps": [{"step_name": "A", "responsible_party": "Ops", "description": _LONG_DESCRIPTION, "dependencies": []}],
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
        "process_steps": [{"step_name": "A", "responsible_party": "Ops", "description": _LONG_DESCRIPTION, "dependencies": []}],
        "metrics": [{"id": "M-001", "metric": "Deployment Frequency", "description": "How often we ship."}],
        "critical_success_factors": [{"id": "CSF-001", "factor": "Automation", "description": "Reduces errors."}],
        "critical_failure_factors": [{"id": "CFF-001", "factor": "Manual changes", "description": "Causes drift."}],
        "reporting_and_analytics": [{"id": "REP-001", "report": "Dashboard", "description": "Shows status."}],
    }
    result = validate_process_json(doc)
    assert result == {"valid": True, "issues": []}
