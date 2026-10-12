from process_toolkit.schema.subprocess_json import save_subprocess_flow, validate_subprocess_flow


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
            {"substep_name": "Draft plan", "description": "Draft the initial plan."},
            {"substep_name": "Review plan", "description": "Review the draft plan."},
        ],
    })
    assert result["valid"]
    assert result["issues"] == []


def test_save_subprocess_flow_refuses_to_write_an_invalid_flow(tmp_path, monkeypatch):
    from process_toolkit import paths
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))

    result = save_subprocess_flow("My Step", {"subprocess_flow": [{"description": "no name"}]})

    assert result["status"] == "ERROR"
    assert "issues" in result
    assert not (tmp_path / "subprocesses").exists() or not list((tmp_path / "subprocesses").glob("*.json"))
