import json

from process_toolkit.requirements_summary.requirements_summary import (
    save_requirements_summary,
    load_requirements_summary,
    update_requirements_summary,
)
from process_toolkit import paths


def test_load_without_a_prior_save_returns_not_found():
    result = load_requirements_summary()
    assert result == {"status": "NOT_FOUND"}


def test_save_then_load_round_trips_the_summary():
    summary = {
        "source_directory": "./vendor-docs",
        "source_files": ["notes.txt"],
        "summary": "Vendor onboarding requires KYC checks.",
        "stakeholders": ["Procurement Lead"],
        "functional_requirements": ["Run KYC checks within 5 business days"],
    }
    result = save_requirements_summary(summary)
    assert result.startswith("SUCCESS:")

    on_disk = json.loads(open(paths.output_path("requirements_summary.json"), encoding="utf-8").read())
    assert on_disk == summary

    loaded = load_requirements_summary()
    assert loaded["status"] == "OK"
    assert loaded["source_directory"] == "./vendor-docs"
    assert loaded["stakeholders"] == ["Procurement Lead"]


def test_save_rejects_non_dict_input():
    result = save_requirements_summary(["not", "a", "dict"])
    assert result.startswith("ERROR:")

    import os
    assert not os.path.exists(paths.output_path("requirements_summary.json"))


def test_save_overwrites_a_previously_saved_summary():
    save_requirements_summary({"summary": "first"})
    save_requirements_summary({"summary": "second"})

    loaded = load_requirements_summary()
    assert loaded["summary"] == "second"


def test_load_returns_error_status_on_corrupt_json():
    path = paths.output_path("requirements_summary.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not-json")

    result = load_requirements_summary()
    assert result["status"] == "ERROR"


def test_load_with_state_prefers_this_sessions_own_summary():
    """
    Two concurrent sessions each have their own state dict. If session A
    saves, then session B saves (overwriting the shared on-disk file),
    session A's own later load must still see A's summary, not B's --
    this is the cross-session-leakage fix.
    """
    session_a, session_b = {}, {}

    save_requirements_summary({"summary": "session A's requirements"}, session_a)
    save_requirements_summary({"summary": "session B's requirements"}, session_b)

    loaded_a = load_requirements_summary(session_a)
    assert loaded_a["summary"] == "session A's requirements"

    loaded_b = load_requirements_summary(session_b)
    assert loaded_b["summary"] == "session B's requirements"

    # The shared file still reflects whichever save happened last -- that
    # single cross-process slot is unchanged, deliberate behavior.
    loaded_no_state = load_requirements_summary()
    assert loaded_no_state["summary"] == "session B's requirements"


def test_load_with_state_falls_back_to_shared_file_if_session_never_saved():
    """A session that never called save itself (e.g. a fresh session
    explicitly asked to reuse a prior run's saved summary) still finds
    the shared file."""
    save_requirements_summary({"summary": "from an earlier run"})

    fresh_session = {}
    loaded = load_requirements_summary(fresh_session)
    assert loaded["status"] == "OK"
    assert loaded["summary"] == "from an earlier run"


def test_update_rejects_non_dict_patch():
    save_requirements_summary({"summary": "first"})
    result = update_requirements_summary(["not", "a", "dict"])
    assert result.startswith("ERROR:")


def test_update_fails_when_nothing_has_been_saved_yet():
    result = update_requirements_summary({"summary": "revised"})
    assert result.startswith("ERROR:")


def test_update_shallow_merges_the_patch_onto_the_existing_summary():
    save_requirements_summary({
        "summary": "first draft",
        "requirements_register": [{"id": "FR-001", "type": "functional", "description": "Allow login."}],
    })

    result = update_requirements_summary({"summary": "corrected draft"})
    assert result.startswith("SUCCESS:")

    loaded = load_requirements_summary()
    assert loaded["summary"] == "corrected draft"
    # untouched key survives the patch
    assert loaded["requirements_register"] == [
        {"id": "FR-001", "type": "functional", "description": "Allow login."},
    ]
    # the status key injected by load must never leak into the persisted file
    on_disk = json.loads(open(paths.output_path("requirements_summary.json"), encoding="utf-8").read())
    assert "status" not in on_disk


def test_update_uses_session_state_when_provided():
    session = {}
    save_requirements_summary({"summary": "first draft"}, session)

    result = update_requirements_summary({"summary": "revised"}, session)
    assert result.startswith("SUCCESS:")

    loaded = load_requirements_summary(session)
    assert loaded["summary"] == "revised"
