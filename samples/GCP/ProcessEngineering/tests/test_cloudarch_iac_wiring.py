"""Regression coverage for the CloudArch_IaC_Pipeline wiring (generate ->
validate loop -> zip/download), mirroring test_pipeline_lock_wiring.py's
own style for the sibling CloudArch_Pipeline: exercises the real lock/
approval-state plumbing without needing a live LLM call, plus the plain
ADK tool-function wrappers around process_toolkit.iac.
"""

import os
import uuid
from types import SimpleNamespace

import pytest

# process_agents.common.agent validates model-provider credentials at
# import time (configure_model_provider) -- the two tests below that reach
# root_agent/build_web_app never issue a real LLM call, so a placeholder
# key is enough (same convention as test_web_service.py/
# test_cloudarch_drawio_mcp.py). setdefault so a real key already present
# in the environment is left untouched.
os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")

from process_toolkit import paths
from process_toolkit.run_lock import acquire_pipeline_lock


def _fake_context(state=None, invocation_id=None):
    return SimpleNamespace(state=state if state is not None else {}, invocation_id=invocation_id or uuid.uuid4().hex)


def _write_conflicting_lock(label: str = "an earlier run") -> None:
    import json
    import time

    with open(paths.output_path("pipeline.lock"), "w", encoding="utf-8") as f:
        json.dump({"label": label, "started_at": time.time(), "token": "someone-elses-token", "pid": 1}, f)


def test_iac_reset_short_circuits_with_content_when_locked():
    from process_agents.cloudarch.cloudarch_iac_pipeline_agent import _reset_iac_approval_state

    _write_conflicting_lock("the cloud architecture pipeline")
    result = _reset_iac_approval_state(_fake_context())

    assert result is not None
    assert result.role == "model"
    assert "the cloud architecture pipeline" in result.parts[0].text


def test_iac_reset_proceeds_normally_with_no_conflicting_lock():
    from process_agents.cloudarch.cloudarch_iac_pipeline_agent import _reset_iac_approval_state

    assert _reset_iac_approval_state(_fake_context()) is None


def test_iac_reset_clears_stale_approval_state_from_an_earlier_unrelated_run():
    from process_agents.cloudarch.cloudarch_iac_pipeline_agent import _reset_iac_approval_state

    with open(paths.output_path("approval.json"), "w", encoding="utf-8") as f:
        f.write('{"status": "JSON APPROVED"}')
    with open(paths.output_path("stop_counter.json"), "w", encoding="utf-8") as f:
        f.write('{"count": 2}')

    assert _reset_iac_approval_state(_fake_context()) is None

    assert not os.path.exists(paths.output_path("approval.json"))
    assert not os.path.exists(paths.output_path("stop_counter.json"))


def test_iac_pipeline_releases_its_lock_once_the_whole_run_ends():
    from process_agents.cloudarch.cloudarch_iac_pipeline_agent import (
        _reset_iac_approval_state,
        cloudarch_iac_pipeline,
    )

    ctx = _fake_context()
    assert _reset_iac_approval_state(ctx) is None

    with pytest.raises(Exception):
        acquire_pipeline_lock("a different pipeline")

    cloudarch_iac_pipeline.after_agent_callback(ctx)
    acquire_pipeline_lock("a different pipeline")  # must not raise -- released


def test_iac_pipeline_structure_matches_generate_validate_then_zip_shape():
    from process_agents.cloudarch.cloudarch_iac_pipeline_agent import cloudarch_iac_pipeline

    assert cloudarch_iac_pipeline.name == "CloudArch_IaC_Pipeline"
    top_level_names = [a.name for a in cloudarch_iac_pipeline.sub_agents]
    assert top_level_names == ["CloudArch_IaC_Review_Loop", "CloudArch_IaC_Zip_Agent"]

    loop = cloudarch_iac_pipeline.sub_agents[0]
    loop_names = [a.name for a in loop.sub_agents]
    assert loop_names == ["CloudArch_IaC_Agent", "CloudArch_IaC_Validator_Agent", "Stop_Controller_CloudArch_IaC"]


def test_iac_pipeline_is_registered_on_root_agent():
    from process_agents.common.agent import root_agent

    names = [a.name for a in root_agent.sub_agents]
    assert "CloudArch_IaC_Pipeline" in names


def test_save_validate_zip_round_trip():
    from process_agents.common.utils import save_iac_files, validate_iac_files, zip_iac_files

    result = save_iac_files({"main.tf": 'resource "null_resource" "x" {}\n'})
    assert result["status"] == "OK"
    assert result["files_written"] == ["main.tf"]

    validated = validate_iac_files()
    assert validated["status"] == "OK"
    assert validated["valid"] is True

    zipped = zip_iac_files()
    assert zipped["status"] == "OK"
    assert os.path.exists(zipped["zip_path"])


def test_validate_iac_files_reports_error_when_nothing_saved():
    from process_agents.common.utils import validate_iac_files

    result = validate_iac_files()
    assert result["status"] == "ERROR"


def test_zip_iac_files_reports_error_when_nothing_saved():
    from process_agents.common.utils import zip_iac_files

    result = zip_iac_files()
    assert result["status"] == "ERROR"


def test_validate_iac_files_surfaces_a_real_syntax_error():
    from process_agents.common.utils import save_iac_files, validate_iac_files

    save_iac_files({"main.tf": "resource { this is not valid hcl"})
    result = validate_iac_files()
    assert result["status"] == "OK"
    assert result["valid"] is False
    assert result["files"][0]["file"] == "main.tf"
    assert result["files"][0]["valid"] is False


def test_cloudarch_iac_download_route_registered():
    from process_agents.common.agent import build_web_app

    web_app = build_web_app(https=False)
    rules = {rule.rule for rule in web_app.url_map.iter_rules()}
    assert "/artifacts/cloudarch_iac/download" in rules
