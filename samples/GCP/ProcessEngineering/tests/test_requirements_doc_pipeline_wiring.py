"""Wiring coverage for Requirements_Doc_Pipeline -- the CREATION
counterpart to Requirements_Summary_Agent: synthesizes a brand-new
requirements register directly from a user's own description (no
directory, no already-saved summary required) and renders it as the
final document in one call. Fixes a real routing gap: a request like
"create a requirements document for a new drug ... based on US/UK
standards ..." previously had no requirements-domain creation path at
all, so the router's generic "create a ... document" matching fell
through to Full_Design_Doc_Pipeline instead. Mirrors the sibling
neuro-san port's own test_requirements_doc_pipeline_wiring.py.
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


class TestPipelineComposition:
    def test_pipeline_stages_are_synthesis_then_pinned_requirements_doc_creation(self):
        from process_agents.common.requirements_doc_pipeline_agent import requirements_doc_pipeline
        from process_agents.common.requirements_synthesis_agent import requirements_synthesis_agent

        stage_names = [a.name for a in requirements_doc_pipeline.sub_agents]
        assert requirements_synthesis_agent.name in stage_names
        doc_stage = next(a for a in requirements_doc_pipeline.sub_agents if "Requirements_Doc_Creation" in a.name)
        # Pinned to schema_type="requirements" -- same mechanism confirmed
        # in test_doc_creation_agent_schema_pinning.py: the LLM-facing tool
        # has no schema_type parameter to see or override.
        import inspect

        doc_tool = doc_stage.pipeline.sub_agents[1].tools[0]
        sig = inspect.signature(doc_tool)
        assert "schema_type" not in sig.parameters

    def test_synthesis_agent_has_no_doc_rendering_tool(self):
        from process_agents.common.requirements_synthesis_agent import requirements_synthesis_agent

        assert len(requirements_synthesis_agent.tools) == 2  # load_directory_context, save_requirements_summary


class TestRootAgentWiring:
    def test_pipeline_is_in_root_agent_sub_agents(self):
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Requirements_Doc_Pipeline" in names


class TestRouterInstructions:
    def test_router_references_the_new_pipeline(self):
        text = _router_text()
        assert "Requirements_Doc_Pipeline" in text

    def test_router_1d_is_distinct_from_file_based_summarization_and_regeneration(self):
        text = _router_text()
        assert "### 1d. REQUIREMENTS DOCUMENT CREATION (FROM A DESCRIPTION)" in text
        assert "is Section 1d (Requirements_Doc_Pipeline), not this section" in text

    def test_multi_intent_priority_mentions_the_new_pipeline(self):
        text = _router_text()
        assert "requirements document from a description → Requirements_Doc_Pipeline" in text
