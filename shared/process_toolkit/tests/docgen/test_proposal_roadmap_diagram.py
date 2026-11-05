import os

import pytest

from process_toolkit import paths
from process_toolkit.docgen.proposal_roadmap_diagram import generate_proposal_roadmap_diagram

SAMPLE_PLAN = [
    {"phase": "Phase 1: Discovery", "timing": "Weeks 1-3", "deliverable": "Architecture doc.",
     "acceptance_criteria": "Client sign-off."},
    {"phase": "Phase 2: Build", "timing": "Weeks 4-8", "deliverable": "Deployed platform.",
     "acceptance_criteria": "UAT passed."},
    {"phase": "Phase 3: Go-Live", "timing": "Weeks 9-10", "deliverable": "Production cutover.",
     "acceptance_criteria": "Two weeks stable."},
]


def test_raises_when_no_usable_phases():
    with pytest.raises(ValueError):
        generate_proposal_roadmap_diagram([], "Vendor Portal")
    with pytest.raises(ValueError):
        generate_proposal_roadmap_diagram([{"timing": "no phase name"}], "Vendor Portal")


def test_generates_a_png_at_the_expected_path():
    out_path = generate_proposal_roadmap_diagram(SAMPLE_PLAN, "Vendor Portal")
    assert out_path == paths.output_path("vendor_portal_roadmap.png")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0


def test_handles_a_single_phase():
    out_path = generate_proposal_roadmap_diagram(SAMPLE_PLAN[:1], "Vendor Portal")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0


def test_ignores_entries_without_a_phase_name():
    out_path = generate_proposal_roadmap_diagram(
        SAMPLE_PLAN + [{"timing": "no phase name"}], "Vendor Portal",
    )
    assert os.path.exists(out_path)
