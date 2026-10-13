import os
import warnings

from process_toolkit.docgen import step_diagrams
from process_toolkit.docgen.step_diagrams import generate_step_diagram_for_step


def test_extract_substeps_supports_known_and_fallback_keys():
    assert step_diagrams._extract_substeps({"flow": [{"name": "A"}]}) == [{"name": "A"}]
    assert step_diagrams._extract_substeps({"other": [{"name": "B"}]}) == [{"name": "B"}]
    assert step_diagrams._extract_substeps(None) == []


def test_lane_and_gateway_detection():
    assert step_diagrams._get_lane({"responsible_party": ["Ops"]}) == "Ops"
    assert step_diagrams._is_gateway({"condition": "approved"})
    assert step_diagrams._is_gateway({"type": "decision"})
    assert not step_diagrams._is_gateway({"type": "task"})


def test_step_diagram_with_long_lane_names_does_not_warn(tmp_path):
    # Not expected to raise -- this is a logged UserWarning on an
    # otherwise successful run -- but it's a real, root-cause-fixable
    # issue (a tight_layout() call that can't reconcile with far-left
    # swimlane-label text), not noise to silence. simplefilter("error")
    # turns the warning into a failure so a regression is caught the
    # same way a raised exception would be.
    subprocess_json = {
        "subprocess_steps": [
            {"step_name": "Draft Pull Request With Full Description", "responsible_party": "Software Developer / Engineer"},
            {"step_name": "Peer Review And Approve Changes", "responsible_party": "Senior Reviewer / Tech Lead"},
            {"step_name": "Run Continuous Integration Pipeline", "responsible_party": "CI/CD Automation System"},
            {"step_name": "Merge To Main Branch And Deploy", "responsible_party": "Release Manager"},
            {"step_name": "Monitor Production Health", "responsible_party": "Site Reliability Engineer"},
        ]
    }

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = generate_step_diagram_for_step(
            "Deploy a New Feature Through the Full GitOps-Driven Sprint Pipeline",
            subprocess_json,
            output_dir=str(tmp_path),
        )
    assert out.endswith(".png")
    assert os.path.exists(out)
