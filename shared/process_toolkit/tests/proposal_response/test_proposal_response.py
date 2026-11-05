import json
import os

from process_toolkit.proposal_response.proposal_response import (
    save_proposal_response,
    load_proposal_response,
    update_proposal_response,
)
from process_toolkit import paths


def test_load_without_a_prior_save_returns_not_found():
    result = load_proposal_response()
    assert result == {"status": "NOT_FOUND"}


def test_save_then_load_round_trips_the_response():
    response = {
        "our_understanding": "The customer needs automated invoice extraction.",
        "compliance_matrix": [{"requirement_id": "FR-001", "response_status": "Fully Compliant",
                                "response": "We support this out of the box."}],
    }
    result = save_proposal_response(response)
    assert result.startswith("SUCCESS:")

    on_disk = json.loads(open(paths.output_path("proposal_response.json"), encoding="utf-8").read())
    assert on_disk == response

    loaded = load_proposal_response()
    assert loaded["status"] == "OK"
    assert loaded["our_understanding"] == "The customer needs automated invoice extraction."


def test_save_rejects_non_dict_input():
    result = save_proposal_response(["not", "a", "dict"])
    assert result.startswith("ERROR:")
    assert not os.path.exists(paths.output_path("proposal_response.json"))


def test_save_overwrites_a_previously_saved_response():
    save_proposal_response({"our_understanding": "first"})
    save_proposal_response({"our_understanding": "second"})

    loaded = load_proposal_response()
    assert loaded["our_understanding"] == "second"


def test_load_returns_error_status_on_corrupt_json():
    path = paths.output_path("proposal_response.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not-json")

    result = load_proposal_response()
    assert result["status"] == "ERROR"


def test_load_with_state_prefers_this_sessions_own_response():
    session_a, session_b = {}, {}

    save_proposal_response({"our_understanding": "session A's response"}, session_a)
    save_proposal_response({"our_understanding": "session B's response"}, session_b)

    loaded_a = load_proposal_response(session_a)
    assert loaded_a["our_understanding"] == "session A's response"

    loaded_b = load_proposal_response(session_b)
    assert loaded_b["our_understanding"] == "session B's response"


def test_update_rejects_non_dict_patch():
    save_proposal_response({"our_understanding": "first"})
    result = update_proposal_response(["not", "a", "dict"])
    assert result.startswith("ERROR:")


def test_update_fails_when_nothing_has_been_saved_yet():
    result = update_proposal_response({"our_understanding": "revised"})
    assert result.startswith("ERROR:")


def test_update_shallow_merges_the_patch_onto_the_existing_response():
    save_proposal_response({
        "our_understanding": "first draft",
        "compliance_matrix": [{"requirement_id": "FR-001", "response_status": "Compliant"}],
    })

    result = update_proposal_response({"our_understanding": "corrected draft"})
    assert result.startswith("SUCCESS:")

    loaded = load_proposal_response()
    assert loaded["our_understanding"] == "corrected draft"
    # untouched key survives the patch
    assert loaded["compliance_matrix"] == [{"requirement_id": "FR-001", "response_status": "Compliant"}]
    # the status key injected by load must never leak into the persisted file
    on_disk = json.loads(open(paths.output_path("proposal_response.json"), encoding="utf-8").read())
    assert "status" not in on_disk


def test_update_uses_session_state_when_provided():
    session = {}
    save_proposal_response({"our_understanding": "first draft"}, session)

    result = update_proposal_response({"our_understanding": "revised"}, session)
    assert result.startswith("SUCCESS:")

    loaded = load_proposal_response(session)
    assert loaded["our_understanding"] == "revised"
