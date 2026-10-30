"""Wiring coverage for Proposal_Response_Pipeline -- drafts a formal
Response to Proposal against an ALREADY-saved requirements summary (an
RFP/proposal's own analyzed requirements register) plus a description of
the responding organization's solution/offering, and renders it as the
final document in one call. Modeled closely on
Requirements_Doc_Pipeline's own shape -- mirrors
test_requirements_doc_pipeline_wiring.py.
"""

import inspect
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
    def test_pipeline_stages_are_synthesis_then_pinned_proposal_response_doc_creation(self):
        from process_agents.common.proposal_response_pipeline_agent import proposal_response_pipeline
        from process_agents.common.proposal_response_agent import proposal_response_agent

        stage_names = [a.name for a in proposal_response_pipeline.sub_agents]
        assert proposal_response_agent.name in stage_names
        doc_stage = next(
            a for a in proposal_response_pipeline.sub_agents if "Proposal_Response_Doc_Creation" in a.name
        )
        # Pinned to schema_type="proposal_response" -- same mechanism
        # confirmed in test_doc_creation_agent_schema_pinning.py: the
        # LLM-facing tool has no schema_type parameter to see or override.
        doc_tool = doc_stage.pipeline.sub_agents[1].tools[0]
        sig = inspect.signature(doc_tool)
        assert "schema_type" not in sig.parameters

    def test_synthesis_agent_has_only_the_two_requirements_proposal_tools(self):
        from process_agents.common.proposal_response_agent import proposal_response_agent

        assert len(proposal_response_agent.tools) == 2  # load_requirements_summary, save_proposal_response

    def test_mute_unmute_clones_are_not_the_shared_singletons(self):
        # Regression guard: reusing the shared mute_agent/unmute_agent
        # singletons directly raises an ADK single-parent ValidationError
        # (Full_Design_Pipeline already claims them) -- confirmed and
        # fixed for Requirements_Doc_Pipeline; this pipeline must use its
        # own fresh clones the same way.
        from process_agents.common.proposal_response_pipeline_agent import (
            proposal_response_pipeline,
            mute_agent_instance,
            unmute_agent_instance,
        )
        from process_agents.common.utils_agent import mute_agent, unmute_agent

        assert mute_agent_instance is not mute_agent
        assert unmute_agent_instance is not unmute_agent
        assert mute_agent_instance in proposal_response_pipeline.sub_agents
        assert unmute_agent_instance in proposal_response_pipeline.sub_agents


class TestRootAgentWiring:
    def test_pipeline_is_in_root_agent_sub_agents(self):
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Proposal_Response_Pipeline" in names


class TestRouterInstructions:
    def test_router_references_the_new_pipeline(self):
        text = _router_text()
        assert "Proposal_Response_Pipeline" in text

    def test_router_1e_exists_and_requires_a_saved_requirements_summary(self):
        text = _router_text()
        assert "### 1e. PROPOSAL RESPONSE DOCUMENT CREATION" in text
        assert "this rule has a hard prerequisite" in text

    def test_router_distinguishes_1e_from_1d(self):
        text = _router_text()
        assert "PRECEDENCE vs. 1d" in text

    def test_multi_intent_priority_mentions_the_new_pipeline(self):
        text = _router_text()
        assert "proposal response from an RFP's analyzed requirements → Proposal_Response_Pipeline" in text

    def test_document_regeneration_section_mentions_the_proposal_response_document(self):
        text = _router_text()
        assert "Regenerate the proposal response document" in text

    def test_section_1c_points_proposal_response_imports_away_from_the_other_import_agents(self):
        text = _router_text()
        assert "a proposal response to Proposal_Response_Pipeline" in text
