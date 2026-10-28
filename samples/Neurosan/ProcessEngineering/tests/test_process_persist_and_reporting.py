"""Consistency fixes applied to process.hocon after the same bug classes
were confirmed live on the sibling design.hocon pipeline (see
test_design_persist_and_reporting.py's own docstring for the full
incident history). process.hocon's Design_Agent builds a meaningfully
smaller document than design.hocon's old HLD+LLD-in-one-pass generator
(no nested low_level_design, no 8-characteristic ISO/IEC 25010 quality
matrix, no sequence_flows), so there's no live-confirmed incident of it
ever failing to persist -- these are preventive/consistency fixes, not
reproductions of an observed failure:

1. Design_Agent now persists a minimal skeleton ({"process_name": ...,
   "process_steps": []} -- confirmed directly against validate_process_
   json's own code that this alone passes) immediately upon confirming a
   fresh generation, before elaborating the full process. Cheap insurance
   against the same "never called persist within the turn" failure mode.
2. Process_Pipeline's step 10 no longer unconditionally claims a Word
   document "was produced, either way" -- it now only claims success if
   generate_process_document's own result started with "SUCCESS:", and
   explicitly forbids describing the process's own content from
   guesswork if nothing was actually produced.
3. Steps 7-9 (subprocess expansion, diagram, document) got an explicit
   MANDATORY block making it unmissable that they always run once the
   review loop stops, for every stop reason -- not just an implicit
   "do this unconditionally" on step 7 alone, which is what design.hocon
   had (text-identical to this, even) right before the orchestrator was
   observed, live, skipping straight to its final report instead.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESS_HOCON = PROJECT_ROOT / "registries" / "process.hocon"


def test_design_agent_persists_a_minimal_skeleton_before_elaborating():
    text = PROCESS_HOCON.read_text(encoding="utf-8")
    assert "Build and persist a\n     MINIMAL SKELETON FIRST" in text


def test_minimal_process_skeleton_actually_passes_validation():
    from process_toolkit.schema.process_json import validate_process_json

    skeleton = {"process_name": "Test Process", "process_steps": []}
    result = validate_process_json(skeleton)
    assert result["valid"] is True, result["issues"]


def test_process_pipeline_never_claims_success_the_tool_itself_denied():
    text = PROCESS_HOCON.read_text(encoding="utf-8")
    assert 'starting with\n   either "SUCCESS:" or "ERROR:"' in text
    assert 'NEVER\n    claim a document was produced "either way"' in text


def test_process_pipeline_never_invents_content_it_cannot_verify():
    text = PROCESS_HOCON.read_text(encoding="utf-8")
    assert "NEVER describe the process's own content" in text
    assert "a process could not be completed and saved this time" in text


def test_process_pipeline_always_runs_subprocess_diagram_and_document():
    text = PROCESS_HOCON.read_text(encoding="utf-8")
    assert "MANDATORY, NO EXCEPTIONS" in text
    assert 'for EVERY\nstop reason including "MAX_ITERATIONS"' in text
    assert "Call all three now, regardless of" in text
