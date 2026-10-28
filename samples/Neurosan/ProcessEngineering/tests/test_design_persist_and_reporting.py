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

A FOURTH bug surfaced on the actual live retry of all three fixes above:
Design_Doc_Pipeline's first command of that chat session STILL never
produced a design_data.json at all (confirmed via the server's own
cli.log: EdgeInference logged "Design document JSON not found" and
create_standard_doc_from_file raised FileNotFoundError on the exact same
path, for that exact run) -- meaning Design_Doc_Agent never reached its
own persist step within that single invocation (most likely stuck
earlier in the build/validate loop and never got that far, rather than
reaching persist and skipping it). The orchestrator's own final report
for that run STILL described specific architecture content ("a
microservices-based architecture... utilizing Kubernetes... RDS and
DynamoDB") that matches neither the user's real uploaded diagram (a
plain 3-tier AWS VPC/ALB/WAF/RDS design) nor anything ever written to
disk -- i.e. the orchestrator fabricated its summary outright rather
than reporting that nothing was actually produced. Two fixes: (a)
Design_Doc_Agent now persists the full document BEFORE validating it
(not only after validation succeeds), so an interrupted pass still
leaves a real, correctable draft on disk instead of nothing; (b) the
orchestrator's step 9 now explicitly forbids describing the design's own
content from guesswork -- if step 7/8 reported a missing design, it must
say so plainly instead of inventing specifics.

A FIFTH bug, found by actually reading persist_final_design_json's own
source (shared/process_toolkit/src/process_toolkit/schema/design_json.py):
it runs validate_design_json INTERNALLY and silently refuses to write
anything that fails -- so fix (a) above, reordering WHEN Design_Doc_Agent
calls persist relative to its OWN separate validate_design_json call,
could never have helped; persist's internal gate blocks either way. Ruled
out as the actual cause here too, though: grep-ing cli.log for
persist_final_design_json's own "failed validation, nothing persisted"
warning across every recent failing run found NONE -- meaning the tool was
never even CALLED, not called-and-rejected. The real failure mode: asking
Design_Doc_Agent to build the ENTIRE Combined HLD+LLD document (every
section, in full detail) before EVER calling persist_final_design_json
once is too large a task to reliably finish in one invocation -- confirmed
across multiple live runs burning their full multi-minute, many-tool-call
budget on reasoning without ever completing a single persist call. Fixed
by checkpoint discipline: persist a MINIMAL SKELETON (document_metadata +
empty {} high_level_design/low_level_design -- confirmed directly against
validate_design_json's own code that this alone passes) as the very next
action after confirming a fresh generation, before elaborating anything
else, then persist again after each major group of sections completed --
never let a single uncheckpointed pass span the whole document.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESIGN_HOCON = PROJECT_ROOT / "registries" / "design.hocon"


def test_design_doc_agent_persists_a_minimal_skeleton_before_elaborating():
    # The actual fix for the "never produced a design json" bug: a
    # trivial, structurally-valid skeleton gets built and persisted as
    # the very first action for a fresh generation, before the agent
    # attempts the much larger task of elaborating every section -- so
    # an interrupted pass still leaves something real and correctable on
    # disk instead of nothing.
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert "CHECKPOINT DISCIPLINE" in text
    assert "Build and persist a MINIMAL SKELETON FIRST" in text
    assert "NEVER wait until the entire document is complete to persist" in text


def test_minimal_skeleton_actually_passes_validation():
    # Confirms the skeleton the instructions describe is not just
    # plausible-sounding -- it genuinely satisfies validate_design_json's
    # real structural checks (document_metadata fields + high_level_design/
    # low_level_design merely needing to be dicts, empty or not).
    from process_toolkit.schema.design_json import validate_design_json

    skeleton = {
        "document_metadata": {
            "document_id": "ARCH-001",
            "document_type": "Combined",
            "system_name": "Test",
            "title": "Test Design",
            "version": "1.0",
            "status": "draft",
            "industry_sector": "Technology",
        },
        "high_level_design": {},
        "low_level_design": {},
    }
    result = validate_design_json(skeleton)
    assert result["valid"] is True, result["issues"]


def test_design_doc_agent_keeps_persisting_after_each_major_group_of_sections():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert "call persist_final_design_json AGAIN with the corrected" in text


def test_design_doc_pipeline_never_invents_architecture_content_it_cannot_verify():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert "NEVER describe the design's own content" in text
    assert "a design could not be completed and saved this time" in text


def test_design_doc_pipeline_never_claims_success_the_tool_itself_denied():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert 'starting with either "SUCCESS:" or "ERROR:"' in text
    assert "NEVER claim a document was produced" in text


def test_design_doc_pipeline_always_generates_the_diagram_and_document():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert "MANDATORY, NO EXCEPTIONS" in text
    assert 'for EVERY stop\nreason including "MAX_ITERATIONS"' in text
    assert "Call both now, regardless of" in text
