"""Regression coverage for a real production bug hit live: asked to build
an HLD from an uploaded cloud architecture diagram, Design_Doc_Pipeline
burned through both revision passes with Compliance_Agent reporting
"architecture_description is empty"/"quality_attributes is empty"/
"high_level_design.components missing" on EVERY pass, then
generate_design_document failed with FileNotFoundError on
output/<session>/design_data.json -- the file never existed on disk at
all. Root cause: Design_Doc_Agent's own baseline (load_master_design_json)
is the empty template until something is actually persisted; its old
instructions said to call persist_final_design_json "only if you actually
changed something" with no explicit carve-out for a FRESH generation
(going from the empty template to a populated document), leaving room for
a confused or overloaded pass to build a document in-memory but never
actually write it -- at which point every subsequent Compliance_Agent/
Simulation_Agent call audits the SAME empty template forever, hits
max_iterations, and the downstream diagram/docgen steps have nothing real
to work from.

A second, independent bug surfaced in the same incident: even though
generate_design_document genuinely returned "ERROR: ..." (confirmed via
coded_tools/design/doc_generation_tool.py's own SUCCESS:/ERROR: string
convention), Design_Doc_Pipeline's final reporting step was instructed to
"mention that a Word document and architecture diagram were produced
either way" -- i.e. to claim success unconditionally regardless of what
the tool actually returned.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESIGN_HOCON = PROJECT_ROOT / "registries" / "design.hocon"


def test_design_doc_agent_persists_unconditionally_on_a_fresh_generation():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert "this call is UNCONDITIONAL" in text
    assert "always persist" in text


def test_design_doc_pipeline_never_claims_success_the_tool_itself_denied():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert 'starting with either "SUCCESS:" or "ERROR:"' in text
    assert "NEVER claim a document was produced" in text
