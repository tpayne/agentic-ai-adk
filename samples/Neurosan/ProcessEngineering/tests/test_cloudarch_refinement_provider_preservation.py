"""Regression coverage for a real reported bug: a chat session with an
established AWS cloud architecture diagram, asked to "optimize the
architecture for cost" (no explicit mention of AWS, "existing", or any
other obvious refinement verb), got an entirely unrelated, freshly
generated AZURE architecture back instead of a cost-optimized revision of
the same AWS diagram -- the diagram's own cloud provider silently flipped.

Root-caused to two compounding issues, both fixed here:
1. CloudArch_Agent (registries/cloudarch.hocon) decided whether to check
   for an existing diagram (Mode 3, Refinement) purely from whether the
   request's WORDING "sounded like" a modification -- a request with no
   obvious "update"/"modify" verb skipped load_drawio entirely, fell
   through to fresh-generation Mode 1/2, and the file's own "design for
   Azure by default" instruction then silently produced an unrelated
   architecture. Fixed by making the load_drawio call -- and defaulting
   to Refinement Mode whenever it finds an existing diagram -- unconditional,
   not phrasing-dependent, and by requiring the loaded diagram's own
   provider to be carried forward rather than re-defaulted.
2. The router (process_architect.hocon) had no explicit precedence rule
   between CloudArch_FinOps_Agent (Section 3d, read-only cost analysis)
   and CloudArch_Pipeline (Section 6, mutates the diagram) for
   cost-optimization phrasing -- "optimize the architecture for cost" is
   ambiguous between the two. Fixed by adding an explicit precedence note
   defaulting such phrasing to the read-only FinOps tool.

These are plain-text instruction files (no Python logic to unit test), so
this suite is content-assertion based, mirroring this project's existing
convention (see test_router_cloudarch_attachment_override.py /
test_regenerate_document.py) -- it locks in that the fix's own key phrases
are present and ns validate (test_hocon_validation.py) continues to pass.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLOUDARCH_HOCON = PROJECT_ROOT / "registries" / "cloudarch.hocon"
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"


def test_cloudarch_agent_checks_for_an_existing_diagram_unconditionally():
    text = CLOUDARCH_HOCON.read_text(encoding="utf-8")
    assert "call load_drawio FIRST to check whether a diagram already" in text
    assert "UNCONDITIONALLY, before judging from the wording alone" in text


def test_cloudarch_agent_defaults_to_refinement_when_a_diagram_exists():
    text = CLOUDARCH_HOCON.read_text(encoding="utf-8")
    assert "DEFAULT TO REFINEMENT MODE for \"request\"" in text
    assert '"optimize this for cost"' in text


def test_cloudarch_agent_preserves_the_loaded_diagrams_own_provider():
    text = CLOUDARCH_HOCON.read_text(encoding="utf-8")
    assert "cloud PROVIDER (AWS/Azure/GCP) MUST be preserved across a" in text
    assert "it must never override" in text


def test_router_has_a_finops_vs_cloudarch_pipeline_precedence_rule():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "Precedence over Section 6 (Cloud Diagram Generation/Modification)" in text
    assert "A request to \"optimize\"/\"reduce the cost of\" the diagram defaults to CloudArch_FinOps_Agent" in text
