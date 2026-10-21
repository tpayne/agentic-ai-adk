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
    # This fixture's own 5 substeps each have a DISTINCT responsible_party
    # -- exactly the shape that used to collapse every node onto the same
    # x=0.0 coordinate (one node per swimlane) and blow the saved canvas
    # up to tens of thousands of inches wide (see
    # test_every_substep_with_a_distinct_responsible_party_stays_a_normal_size
    # below for the full story) -- a sane file size here is was already
    # being silently violated by this exact fixture before that was fixed.
    assert os.path.getsize(out) < 2_000_000


def test_every_substep_with_a_distinct_responsible_party_stays_a_normal_size(tmp_path):
    # Regression test, confirmed directly against a real generated
    # request: when EVERY substep has its own distinct responsible_party,
    # the swimlane layout (pos[n] = (i * 4.0, lane_y[lane] * 4.0)) gives
    # every single node i=0 within its own one-item lane -- every node's
    # x coordinate is the numerically identical 0.0. matplotlib's own
    # autoscale then collapses the x-axis to a near-zero-width range, and
    # bbox_inches="tight" (at save time) becomes numerically unstable
    # fitting real, fixed-size text/label artists against that
    # near-singular data-to-display scale: one real generated diagram
    # measured 18438in x 8.7in -- 3.69 BILLION pixels at this module's
    # own 150dpi, a 14MB+ file no image viewer could open. savefig()
    # itself never raises for this, so it fails completely silently
    # without a check like this one.
    subprocess_json = {
        "subprocess_flow": [
            {"substep_name": "Target Identification", "responsible_party": "Senior Research Scientist"},
            {"substep_name": "Target Validation", "responsible_party": "Molecular Biologist"},
            {"substep_name": "Assay Development", "responsible_party": "HTS Specialist"},
            {"substep_name": "Hit-to-Lead Optimization", "responsible_party": "Medicinal Chemist"},
            {"substep_name": "Lead Optimization", "responsible_party": "Medicinal Chemist / Pharmacologist"},
            {"substep_name": "Candidate Selection", "responsible_party": "Chief Scientific Officer"},
        ]
    }
    out = generate_step_diagram_for_step(
        "Discovery and Target Identification", subprocess_json, output_dir=str(tmp_path),
    )
    assert out.endswith(".png")
    assert os.path.getsize(out) < 2_000_000

    from PIL import Image
    with Image.open(out) as im:
        width, height = im.size
    assert width < 10_000
    assert height < 10_000
