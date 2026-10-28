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

A THIRD bug surfaced on the very next live retry, after both fixes above
were already in place: Design_Doc_Agent correctly persisted a real,
well-grounded design this time (confirmed directly against the session's
own design_data.json -- real components, business_context.purpose
correctly stating no business purpose was provided, no fabrication) and
Compliance_Agent/Simulation_Agent ran against it for real -- but the run
still hit max_iterations with open compliance feedback, and the
orchestrator skipped straight to its final report without EVER calling
generate_design_flow_diagram or generate_design_document, even though
both tools work fine unconditionally against whatever design_data.json
currently holds (confirmed directly: manually invoking
create_standard_doc_from_file against that exact session's persisted
design succeeded immediately). The old "If verdict is STOP: proceed to
step 7" wording was apparently too easy to silently skip once the stop
reason was "MAX_ITERATIONS" rather than "APPROVED" -- replaced with an
unmissable, explicitly-labeled MANDATORY block spelling out that open
review feedback is input for a FUTURE revision, never a reason to
withhold the diagram/document for the design that exists right now.
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


def test_design_doc_pipeline_always_generates_the_diagram_and_document():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert "MANDATORY, NO EXCEPTIONS" in text
    assert 'for EVERY stop\nreason including "MAX_ITERATIONS"' in text
    assert "Call both now, regardless of" in text
