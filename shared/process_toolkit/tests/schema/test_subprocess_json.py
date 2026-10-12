from process_toolkit.schema.subprocess_json import save_subprocess_flow, validate_subprocess_flow

_LONG_SUBSTEP_DESCRIPTION = (
    "The responsible team works through this sub-step end to end, taking the listed inputs, "
    "applying the required process, and producing the outputs needed for the next sub-step to begin."
)


def test_validate_rejects_missing_substep_name_and_description():
    result = validate_subprocess_flow({"subprocess_flow": [{"description": "does a thing"}]})
    assert not result["valid"]
    assert any("substep_name" in issue["location"] for issue in result["issues"])


def test_validate_rejects_empty_subprocess_flow():
    result = validate_subprocess_flow({"subprocess_flow": []})
    assert not result["valid"]


def test_validate_accepts_well_formed_flow():
    result = validate_subprocess_flow({
        "subprocess_flow": [
            {
                "substep_name": "Draft plan", "description": _LONG_SUBSTEP_DESCRIPTION,
                "purpose": "Produce a first draft to review.", "scope": "Team level",
                "process_owner": "Lead", "responsible_party": "Team",
            },
            {
                "substep_name": "Review plan", "description": _LONG_SUBSTEP_DESCRIPTION,
                "purpose": "Catch issues before execution.", "scope": "Team level",
                "process_owner": "Lead", "responsible_party": "Team",
            },
        ],
    })
    assert result["valid"]
    assert result["issues"] == []


def test_validate_rejects_a_substep_missing_purpose_scope_owner_or_responsible_party():
    result = validate_subprocess_flow({
        "subprocess_flow": [
            {"substep_name": "Draft plan", "description": _LONG_SUBSTEP_DESCRIPTION},
        ],
    })
    assert not result["valid"]
    for field in ("purpose", "scope", "process_owner", "responsible_party"):
        assert any(
            issue["location"] == f"subprocess_flow[0].{field}" for issue in result["issues"]
        ), f"expected a missing-{field} issue"


def test_save_subprocess_flow_refuses_to_write_an_invalid_flow(tmp_path, monkeypatch):
    from process_toolkit import paths
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))

    result = save_subprocess_flow("My Step", {"subprocess_flow": [{"description": "no name"}]})

    assert result["status"] == "ERROR"
    assert "issues" in result
    assert not (tmp_path / "subprocesses").exists() or not list((tmp_path / "subprocesses").glob("*.json"))
