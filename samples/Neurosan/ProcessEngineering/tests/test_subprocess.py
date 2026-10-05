from coded_tools.process.process_json_tool import PersistFinalJsonCodedTool
from coded_tools.process.subprocess_tool import LoadProcessStepsCodedTool, SaveSubprocessFlowCodedTool


def _seed_process():
    doc = {
        "process_name": "Onboarding",
        "process_steps": [{"step_name": "KYC Check", "responsible_party": "Compliance", "dependencies": []}],
    }
    PersistFinalJsonCodedTool().invoke({"json_content": doc}, {})


def test_load_process_steps_returns_the_current_designs_steps():
    _seed_process()
    result = LoadProcessStepsCodedTool().invoke({}, {})
    assert result["process_steps"][0]["step_name"] == "KYC Check"


def test_load_process_steps_returns_empty_list_when_no_design_exists():
    result = LoadProcessStepsCodedTool().invoke({}, {})
    assert result["process_steps"] == []


def test_save_subprocess_flow_persists_to_a_file_named_after_the_step():
    import os

    flow = {"step_name": "KYC Check", "subprocess_flow": [{"substep_name": "Collect ID"}]}
    result = SaveSubprocessFlowCodedTool().invoke({"step_name": "KYC Check", "subprocess_flow": flow}, {})

    assert result["status"] == "OK"
    assert os.path.exists(result["path"])
    assert result["path"].endswith("KYC_Check.json")


def test_save_subprocess_flow_sanitizes_a_path_traversal_attempt():
    """A step_name is untrusted, LLM-generated content -- it must never be
    able to escape the subprocesses output directory."""
    result = SaveSubprocessFlowCodedTool().invoke(
        {"step_name": "../../etc/evil", "subprocess_flow": {"step_name": "x", "subprocess_flow": []}}, {}
    )
    assert result["status"] == "OK"
    assert "subprocesses" in result["path"]
    assert ".." not in result["path"]


def test_save_subprocess_flow_requires_both_arguments():
    result = SaveSubprocessFlowCodedTool().invoke({"step_name": "KYC Check"}, {})
    assert result["status"] == "ERROR"
