"""Wiring coverage for the standalone Infrastructure-as-Code generation
network (registries/cloudarch_iac.hocon): generates IaC for the current
cloud architecture diagram, validates its syntax with a real parser, zips
it, and makes it downloadable.

`ns validate` (test_hocon_validation.py) and test_coded_tool_class_
resolution.py already guard every network's "class" references generically
against the AGENT_TOOL_PATH resolution failure documented in
test_cloudarch_import_wiring.py's own module docstring. The identity checks
below lock in specifically that THIS network's own shims re-export the
real canonical classes rather than forked copies -- reset_loop_state_tool
and loop_control_tool deliberately re-export the SHARED, non-lock-
releasing common/ versions (not cloudarch.hocon's own customized,
lock-releasing ones), since this pipeline has genuine steps (zip, download)
after its own review loop stops -- see cloudarch_iac.hocon's own module
comment for why releasing early here would be premature.
"""

from pathlib import Path

import pytest

from coded_tools.common.reset_loop_state_base import ResetLoopStateCodedTool as CanonicalResetLoopState
from coded_tools.common.loop_control import LoopControlCodedTool as CanonicalLoopControl
from coded_tools.cloudarch.load_drawio_tool import LoadDrawioCodedTool as CanonicalLoadDrawio
from coded_tools.cloudarch.load_iteration_feedback_tool import (
    LoadIterationFeedbackCodedTool as CanonicalLoadIterationFeedback,
)
from coded_tools.cloudarch.save_iteration_feedback_tool import (
    SaveIterationFeedbackCodedTool as CanonicalSaveIterationFeedback,
)
from coded_tools.process_architect.download_artifact_tool import (
    DownloadArtifactCodedTool as CanonicalDownloadArtifact,
)

from coded_tools.cloudarch_iac.reset_loop_state_tool import ResetLoopStateCodedTool
from coded_tools.cloudarch_iac.loop_control_tool import LoopControlCodedTool
from coded_tools.cloudarch_iac.load_drawio_tool import LoadDrawioCodedTool
from coded_tools.cloudarch_iac.load_iteration_feedback_tool import LoadIterationFeedbackCodedTool
from coded_tools.cloudarch_iac.save_iteration_feedback_tool import SaveIterationFeedbackCodedTool
from coded_tools.cloudarch_iac.download_artifact_tool import DownloadArtifactCodedTool
from coded_tools.cloudarch_iac.iac_tool import (
    SaveIacFilesCodedTool,
    ValidateIacFilesCodedTool,
    ZipIacFilesCodedTool,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_cloudarch_iac_shims_reexport_the_canonical_classes():
    assert ResetLoopStateCodedTool is CanonicalResetLoopState
    assert LoopControlCodedTool is CanonicalLoopControl
    assert LoadDrawioCodedTool is CanonicalLoadDrawio
    assert LoadIterationFeedbackCodedTool is CanonicalLoadIterationFeedback
    assert SaveIterationFeedbackCodedTool is CanonicalSaveIterationFeedback
    assert DownloadArtifactCodedTool is CanonicalDownloadArtifact


def test_router_references_the_cloudarch_iac_network():
    router_text = (PROJECT_ROOT / "registries" / "process_architect.hocon").read_text(encoding="utf-8")
    assert "CloudArch_IaC_Pipeline" in router_text
    assert '"/cloudarch_iac"' in router_text


def test_manifest_registers_the_cloudarch_iac_network():
    manifest_text = (PROJECT_ROOT / "registries" / "manifest.hocon").read_text(encoding="utf-8")
    assert '"cloudarch_iac.hocon"' in manifest_text


def test_save_validate_zip_round_trip(tmp_path, monkeypatch):
    from process_toolkit import paths

    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))

    save_result = SaveIacFilesCodedTool().invoke({"files": {"main.tf": 'resource "null_resource" "x" {}\n'}}, {})
    assert save_result["status"] == "OK"
    assert save_result["files_written"] == ["main.tf"]

    validate_result = ValidateIacFilesCodedTool().invoke({}, {})
    assert validate_result["status"] == "OK"
    assert validate_result["valid"] is True

    zip_result = ZipIacFilesCodedTool().invoke({}, {})
    assert zip_result["status"] == "OK"
    assert (tmp_path / "cloudarch_iac.zip").exists()


def test_validate_iac_files_reports_error_when_nothing_saved(tmp_path, monkeypatch):
    from process_toolkit import paths

    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    result = ValidateIacFilesCodedTool().invoke({}, {})
    assert result["status"] == "ERROR"


def test_zip_iac_files_reports_error_when_nothing_saved(tmp_path, monkeypatch):
    from process_toolkit import paths

    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    result = ZipIacFilesCodedTool().invoke({}, {})
    assert result["status"] == "ERROR"


def test_save_iac_files_rejects_a_non_dict_or_empty_files_argument():
    tool = SaveIacFilesCodedTool()
    assert tool.invoke({"files": "not-a-dict"}, {})["status"] == "ERROR"
    assert tool.invoke({"files": {}}, {})["status"] == "ERROR"
    assert tool.invoke({}, {})["status"] == "ERROR"
