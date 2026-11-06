import json

from process_toolkit.test_specification.test_specification import (
    save_test_specification,
    load_test_specification,
    update_test_specification,
)
from process_toolkit import paths


def test_load_without_a_prior_save_returns_not_found():
    result = load_test_specification()
    assert result == {"status": "NOT_FOUND"}


def test_save_then_load_round_trips_the_specification():
    specification = {
        "name": "MetroLink Test Specification",
        "source_requirements_used": True,
        "summary": "Validates the MetroLink vendor onboarding requirements.",
        "test_cases": [{"id": "TC-001", "type": "functional", "description": "Login works."}],
    }
    result = save_test_specification(specification)
    assert result.startswith("SUCCESS:")

    on_disk = json.loads(open(paths.output_path("test_specification.json"), encoding="utf-8").read())
    assert on_disk == specification

    loaded = load_test_specification()
    assert loaded["status"] == "OK"
    assert loaded["name"] == "MetroLink Test Specification"
    assert loaded["test_cases"] == [{"id": "TC-001", "type": "functional", "description": "Login works."}]


def test_save_rejects_non_dict_input():
    result = save_test_specification(["not", "a", "dict"])
    assert result.startswith("ERROR:")

    import os
    assert not os.path.exists(paths.output_path("test_specification.json"))


def test_save_overwrites_a_previously_saved_specification():
    save_test_specification({"summary": "first"})
    save_test_specification({"summary": "second"})

    loaded = load_test_specification()
    assert loaded["summary"] == "second"


def test_load_returns_error_status_on_corrupt_json():
    path = paths.output_path("test_specification.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not-json")

    result = load_test_specification()
    assert result["status"] == "ERROR"


def test_load_with_state_prefers_this_sessions_own_specification():
    session_a, session_b = {}, {}

    save_test_specification({"summary": "session A's test spec"}, session_a)
    save_test_specification({"summary": "session B's test spec"}, session_b)

    loaded_a = load_test_specification(session_a)
    assert loaded_a["summary"] == "session A's test spec"

    loaded_b = load_test_specification(session_b)
    assert loaded_b["summary"] == "session B's test spec"

    loaded_no_state = load_test_specification()
    assert loaded_no_state["summary"] == "session B's test spec"


def test_load_with_state_falls_back_to_shared_file_if_session_never_saved():
    save_test_specification({"summary": "from an earlier run"})

    fresh_session = {}
    loaded = load_test_specification(fresh_session)
    assert loaded["status"] == "OK"
    assert loaded["summary"] == "from an earlier run"


def test_update_rejects_non_dict_patch():
    save_test_specification({"summary": "first"})
    result = update_test_specification(["not", "a", "dict"])
    assert result.startswith("ERROR:")


def test_update_fails_when_nothing_has_been_saved_yet():
    result = update_test_specification({"summary": "revised"})
    assert result.startswith("ERROR:")


def test_update_shallow_merges_the_patch_onto_the_existing_specification():
    save_test_specification({
        "summary": "first draft",
        "test_cases": [{"id": "TC-001", "type": "functional", "description": "Login works."}],
    })

    result = update_test_specification({"summary": "corrected draft"})
    assert result.startswith("SUCCESS:")

    loaded = load_test_specification()
    assert loaded["summary"] == "corrected draft"
    assert loaded["test_cases"] == [{"id": "TC-001", "type": "functional", "description": "Login works."}]

    on_disk = json.loads(open(paths.output_path("test_specification.json"), encoding="utf-8").read())
    assert "status" not in on_disk


def test_update_uses_session_state_when_provided():
    session = {}
    save_test_specification({"summary": "first draft"}, session)

    result = update_test_specification({"summary": "revised"}, session)
    assert result.startswith("SUCCESS:")

    loaded = load_test_specification(session)
    assert loaded["summary"] == "revised"
