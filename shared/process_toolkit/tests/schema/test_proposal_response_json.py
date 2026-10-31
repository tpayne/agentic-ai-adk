from process_toolkit.schema.proposal_response_json import (
    PROPOSAL_RESPONSE_FILENAME,
    load_proposal_response_template,
    validate_proposal_response,
)


def test_proposal_response_filename_matches_the_real_persistence_module():
    # Guards against drift between this module's own re-export and the
    # real filename proposal_response.py actually saves/loads.
    from process_toolkit.proposal_response.proposal_response import (
        PROPOSAL_RESPONSE_FILENAME as CANONICAL_FILENAME,
    )

    assert PROPOSAL_RESPONSE_FILENAME == CANONICAL_FILENAME


def test_load_proposal_response_template_is_a_fresh_copy_each_time():
    a = load_proposal_response_template()
    b = load_proposal_response_template()
    assert a == b
    a["summary"] = "mutated"
    assert b["summary"] == ""


def test_validate_rejects_non_dict_input():
    result = validate_proposal_response("not a dict")
    assert not result["valid"]
    assert result["issues"][0]["location"] == "$"


def test_validate_accepts_a_well_formed_response():
    doc = {
        "compliance_matrix": [
            {
                "requirement_id": "FR-001",
                "requirement_text": "Allow login.",
                "requirement_type": "functional",
                "response_status": "Fully Compliant",
                "response": "Our solution supports SSO-based login.",
            },
        ],
    }
    result = validate_proposal_response(doc)
    assert result == {"valid": True, "issues": []}


def test_validate_accepts_no_compliance_matrix_at_all():
    assert validate_proposal_response({"summary": "A proposal response."}) == {"valid": True, "issues": []}


def test_validate_rejects_a_non_list_compliance_matrix():
    result = validate_proposal_response({"compliance_matrix": "not a list"})
    assert not result["valid"]
    assert result["issues"][0]["location"] == "$.compliance_matrix"


def test_validate_requires_a_requirement_id_for_each_entry():
    doc = {"compliance_matrix": [{"response_status": "Fully Compliant"}]}
    result = validate_proposal_response(doc)
    assert not result["valid"]
    assert any(
        issue["location"] == "$.compliance_matrix[0]" and "requirement_id" in issue["issue"]
        for issue in result["issues"]
    )


def test_validate_rejects_an_unrecognized_response_status():
    doc = {"compliance_matrix": [{"requirement_id": "FR-001", "response_status": "Maybe"}]}
    result = validate_proposal_response(doc)
    assert not result["valid"]
    assert any(
        issue["location"] == "$.compliance_matrix[0].response_status" for issue in result["issues"]
    )


def test_validate_rejects_a_non_dict_entry():
    doc = {"compliance_matrix": ["not a dict"]}
    result = validate_proposal_response(doc)
    assert not result["valid"]
    assert any(issue["location"] == "$.compliance_matrix[0]" for issue in result["issues"])
