"""Mirrors the Neuro-San sibling port's fix for a confirmed real production
bug (identical router logic, developed in tandem with this one): a request
phrased as "review this architecture for me and tell me what it does. Keep
it for future use in the session" -- with an attached cloudarch_drawio.xml
file, but no "cloud"/"diagram"/"drawio" word anywhere in the text itself --
fell through the router's bare-"architecture"-defaults-to-DESIGN-DOCUMENT
rule and routed to Full_Design_Doc_Pipeline, which would build an entirely
new design document from the diagram's content instead of restoring/
explaining the diagram itself. The diagram would never be persisted as that
session's own cloudarch_drawio.xml, so every subsequent cloud-architecture-
specific command (consultant, simulation, attack simulation, cost
estimation) would then fail for lack of a diagram.

Three-part fix, same as the neuro-san port's registries/process_architect.hocon:
1. An attachment literally named "cloudarch_drawio.xml" (or recognizably
   drawio/mxGraph XML content) is now an explicit override, checked BEFORE
   the word-based DOMAIN DISAMBIGUATION signals -- it forces the CLOUD
   ARCHITECTURE DIAGRAM domain even when the prose itself has no
   cloud/diagram/drawio word.
2. Section 1b (DESIGN DOCUMENT CREATION) now explicitly requires an actual
   creation verb -- an attached diagram plus bare "architecture" wording,
   with the user only asking to review/explain/keep it, no longer qualifies.
3. Section 1c's import/restore trigger now recognizes "keep/save/retain ...
   for future use" as import intent even without the literal word "import",
   and CloudArch_Import_Agent's own STEP 5 now actually describes the
   diagram's content (grounded in the XML, same discipline as
   CloudArch_Consultant_Agent) rather than only confirming the restore -- so
   a single call satisfies both the "keep it" and "tell me what it does"
   halves of the request.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTER_INSTRUCTIONS = PROJECT_ROOT / "instructions" / "common" / "agent.txt"
CLOUDARCH_IMPORT_INSTRUCTIONS = PROJECT_ROOT / "instructions" / "cloudarch" / "import_agent.txt"


def test_attached_diagram_overrides_bare_architecture_wording():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "ATTACHED-FILE OVERRIDE" in text
    assert 'is ALWAYS a CLOUD\nARCHITECTURE DIAGRAM domain signal' in text


def test_design_document_creation_requires_an_actual_creation_verb():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "requires an actual CREATION verb" in text
    assert "do not build a brand-new design document just because a diagram\nwas attached" in text


def test_keep_for_future_use_is_recognized_as_import_intent():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert '"keep/save/retain this [diagram/architecture] for future\nuse/reference"' in text
    assert "Review this architecture for me and tell me what it does" in text


def test_cloudarch_import_agent_describes_what_it_restored():
    text = CLOUDARCH_IMPORT_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "ALSO describe what it actually depicts" in text
    assert "This is not optional even when the user's own request only asked you to\nrestore/keep it" in text
