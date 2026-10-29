"""Regression coverage for a real reported bug: a chat session with an
established AWS cloud architecture diagram, asked to "optimize the
architecture for cost" (no explicit mention of AWS, "existing", or any
other obvious refinement verb), got an entirely unrelated, freshly
generated AZURE architecture back instead of a cost-optimized revision of
the same AWS diagram -- the diagram's own cloud provider silently flipped.

Root-caused to two compounding issues, both fixed here:
1. CloudArch_Agent (instructions/cloudarch/cloudarch_agent.txt) decided
   whether to check for an existing diagram (Mode 3, Refinement) purely
   from whether the request's WORDING "sounded like" a modification -- a
   request with no obvious "update"/"modify" verb skipped load_drawio
   entirely, fell through to fresh-generation Mode 1/2, and the file's
   own "design for Azure by default" instruction then silently produced
   an unrelated architecture. Fixed by making the load_drawio call -- and
   defaulting to Refinement Mode whenever it finds an existing diagram --
   unconditional, not phrasing-dependent, and by requiring the loaded
   diagram's own provider to be carried forward rather than re-defaulted.
2. The router (instructions/common/agent.txt) had no explicit precedence
   rule between CloudArch_FinOps_Agent (Section 3d, read-only cost
   analysis) and CloudArch_Pipeline (Section 7, mutates the diagram) for
   cost-optimization phrasing -- "optimize the architecture for cost" is
   ambiguous between the two. Fixed by adding an explicit precedence note
   defaulting such phrasing to the read-only FinOps tool.

These are plain-text instruction files (no Python logic to unit test), so
this suite is content-assertion based, mirroring this project's existing
convention (see test_router_cloudarch_attachment_override.py on the
neuro-san port) -- it locks in that the fix's own key phrases are present.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLOUDARCH_AGENT_TXT = PROJECT_ROOT / "instructions" / "cloudarch" / "cloudarch_agent.txt"
ROUTER_TXT = PROJECT_ROOT / "instructions" / "common" / "agent.txt"


def test_cloudarch_agent_checks_for_an_existing_diagram_unconditionally():
    text = CLOUDARCH_AGENT_TXT.read_text(encoding="utf-8")
    assert "CALL load_drawio FIRST (no visible commentary) to check whether a diagram already" in text
    assert "UNCONDITIONALLY, before judging from the wording alone" in text
    assert "ALWAYS CALL load_drawio next, with no visible commentary, REGARDLESS of whether" in text


def test_cloudarch_agent_defaults_to_refinement_when_a_diagram_exists():
    text = CLOUDARCH_AGENT_TXT.read_text(encoding="utf-8")
    assert "DEFAULT TO REFINEMENT MODE for the current request" in text
    assert '"optimize this for cost"' in text


def test_cloudarch_agent_preserves_the_loaded_diagrams_own_provider():
    text = CLOUDARCH_AGENT_TXT.read_text(encoding="utf-8")
    assert "cloud PROVIDER (AWS/Azure/GCP) MUST be preserved across a" in text
    assert "it must never override" in text


def test_azure_default_is_explicitly_scoped_to_no_existing_diagram():
    # The "design for Azure by default" rule lives at the TOP of the file,
    # read regardless of which numbered mode ends up handling a request --
    # it must carry its own "only with no existing diagram" scope right
    # there, not rely solely on Mode 3's own caveat further down, since a
    # request could be classified into a DIFFERENT mode (5/6) that never
    # re-reads Mode 3's text at all.
    text = CLOUDARCH_AGENT_TXT.read_text(encoding="utf-8")
    assert "THIS DEFAULT APPLIES\nONLY WHEN NO CLOUD ARCHITECTURE DIAGRAM ALREADY EXISTS" in text
    assert "must never silently switch cloud providers out from under them" in text


def test_directory_and_requirements_summary_modes_defer_to_refinement():
    # Regression test for a residual gap found during review: Modes 5/6
    # (Directory Context / Saved Requirements Summary) described
    # themselves purely as "source material for THIS GENERATION," with no
    # acknowledgment that an existing diagram (Mode 3) might already be
    # active -- a request combining a directory/summary reference with an
    # implicit update to an existing diagram could have bypassed Mode 3's
    # own provider-preservation guarantee entirely. Both modes must now
    # explicitly defer to Mode 3 when it applies.
    text = CLOUDARCH_AGENT_TXT.read_text(encoding="utf-8")
    assert text.count("INTERACTION WITH MODE 3") == 2


def test_router_has_a_finops_vs_cloudarch_pipeline_precedence_rule():
    text = ROUTER_TXT.read_text(encoding="utf-8")
    assert "Precedence over Section 7 (Cloud Diagram Generation/Modification)" in text
    assert "A request to \"optimize\"/\"reduce the cost of\" the diagram defaults to CloudArch_FinOps_Agent" in text
