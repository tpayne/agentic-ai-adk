"""Wiring coverage for splitting design document rendering into two
SEPARATE .docx files (HLD and LLD) instead of one combined document, with
the ability to ask for just the HLD, just the LLD, or both -- for both
creation (Full_Design_Doc_Pipeline's own render stage) and regeneration
(Create_Doc_Agent). design_data.json's own schema/generation logic is
unaffected -- this is purely a rendering-selection change threaded
through doc_creation_agent.py's pinned closure (schema_type="design"
only) and doc_generation_agent.txt's own wording-inference instructions,
both of which automatically cover the creation pipeline's Stage 4 AND the
fully-generic regeneration path since they share the same mechanism.

See process_toolkit.docgen.generation's own _build_design_documents/
_resolve_design_variant for the actual rendering logic (shared with the
sibling Neuro-San port), and test_doc_creation_agent_schema_pinning.py
for the pinned-closure design_variant exposure coverage.
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _instruction_text(relative_path: str) -> str:
    path = os.path.join(ROOT, "instructions", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _router_text() -> str:
    return _instruction_text("common/agent.txt")


class TestRouterInstructions:
    def test_design_creation_section_notes_the_pipeline_self_determines_the_variant(self):
        text = _router_text()
        assert "### 1b. DESIGN DOCUMENT CREATION" in text
        idx = text.index("### 1b. DESIGN DOCUMENT CREATION")
        next_section = text.index("### 1c.", idx)
        section_text = text[idx:next_section]
        assert "separate Word documents" in section_text
        assert "never one combined file" in section_text

    def test_document_regeneration_section_has_an_hld_and_an_lld_example(self):
        text = _router_text()
        assert "### 1b." not in text[text.index("## 6. DOCUMENT REGENERATION"):]  # sanity: really Section 6
        idx = text.index("## 6. DOCUMENT REGENERATION")
        next_section = text.index("## 7.", idx)
        section_text = text[idx:next_section]
        assert "Please regenerate the HLD document" in section_text
        assert "Please regenerate just the LLD." in section_text
        assert "never one combined file" in section_text


class TestDocGenerationAgentInstructions:
    def test_infers_design_variant_from_wording_the_same_way_schema_type_is(self):
        text = _instruction_text("common/doc_generation_agent.txt")
        assert "design_variant" in text
        assert 'design_variant="hld"' in text
        assert 'design_variant="lld"' in text
        assert 'design_variant="both"' in text
        # Mirrors the EXISTING schema_type inference pattern's own
        # conditional phrasing -- confirms this isn't a separate,
        # inconsistent mechanism.
        assert "If this tool exposes a schema_type parameter" in text
        assert "If this tool ALSO exposes a design_variant parameter" in text

    def test_final_confirmation_names_which_documents_were_actually_produced(self):
        text = _instruction_text("common/doc_generation_agent.txt")
        assert "never assume both always exist" in text


class TestDesignDocCreatePipelineUnaffectedCallSite:
    def test_stage_4_call_site_is_unchanged_still_pinned_to_schema_type_design_only(self):
        # Confirms the plan's own "zero changes needed to the Stage-4 call
        # site" claim: the pinned closure gaining a design_variant
        # parameter is entirely internal to doc_creation_agent.py -- the
        # pipeline itself never needs to pass or even know about it.
        path = os.path.join(ROOT, "process_agents", "design", "design_doc_create_agent.py")
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        assert 'build_doc_creation_agent("CreateDoc", schema_type="design")' in text
        assert "design_variant" not in text
