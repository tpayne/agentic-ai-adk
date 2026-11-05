"""Wiring coverage for the two new standalone, on-demand proposal-response
agents: Proposal_Response_Consultant_Agent (narrative Q&A over a saved
proposal response) and Proposal_Response_Reviewer_Agent (quality audit,
with an intent-gated update_proposal_response tool). Both mirror
Requirements_Consultant_Agent/Requirements_Reviewer_Agent's shape --
see test_requirements_reviewer_simulation_wiring.py for the analogous
requirements-side coverage, and the sibling neuro-san port's own
test_proposal_response_consultant_reviewer_wiring.py.
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


class TestAgentsUseTheCanonicalLoadProposalResponseTool:
    def test_consultant_and_reviewer_share_the_same_load_tool(self):
        from process_agents.common.proposal_response_consultant_agent import (
            proposal_response_consultant_agent,
        )
        from process_agents.common.proposal_response_reviewer_agent import (
            proposal_response_reviewer_agent,
        )
        from process_agents.common.utils import load_proposal_response

        assert load_proposal_response in proposal_response_consultant_agent.tools
        assert load_proposal_response in proposal_response_reviewer_agent.tools

    def test_only_the_reviewer_also_has_the_update_tool(self):
        from process_agents.common.proposal_response_consultant_agent import (
            proposal_response_consultant_agent,
        )
        from process_agents.common.proposal_response_reviewer_agent import (
            proposal_response_reviewer_agent,
        )
        from process_agents.common.utils import load_proposal_response, update_proposal_response

        assert set(proposal_response_consultant_agent.tools) == {load_proposal_response}
        assert set(proposal_response_reviewer_agent.tools) == {
            load_proposal_response,
            update_proposal_response,
        }


class TestRootAgentWiring:
    def test_both_new_agents_are_in_root_agent_sub_agents(self):
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Proposal_Response_Consultant_Agent" in names
        assert "Proposal_Response_Reviewer_Agent" in names


class TestRouterInstructions:
    def test_router_references_both_new_agents(self):
        text = _router_text()
        assert "Proposal_Response_Consultant_Agent" in text
        assert "Proposal_Response_Reviewer_Agent" in text

    def test_router_disambiguates_proposal_response_review_from_the_consultant(self):
        text = _router_text()
        assert "PRECEDENCE vs. 4f" in text

    def test_router_mentions_review_and_fix_routes_to_the_same_agent(self):
        text = _router_text()
        assert text.count("it is the SAME agent for both modes") == 2

    def test_router_multi_intent_priority_mentions_both_new_agents(self):
        text = _router_text()
        assert "saved proposal response → Proposal_Response_Consultant_Agent" in text
        assert "proposal response quality → Proposal_Response_Reviewer_Agent" in text


def test_both_reviewer_agents_produce_one_combined_reply_in_apply_mode():
    # Confirmed live bug (sibling neuro-san port, identical instruction
    # pattern): a separate "REPLY" section (full audit report, closing
    # with a one-line verdict) and a separate "APPLY MODE... report
    # exactly what changed" instruction were stacked, not merged. In
    # apply mode the agent dutifully produced BOTH blocks back to back,
    # and wherever they got joined dropped the paragraph break entirely
    # (e.g. "...final solution scoping."**I have updated the proposal
    # response as requested." with zero separator).
    for relative_path in ("common/requirements_reviewer_agent.txt", "common/proposal_response_reviewer_agent.txt"):
        text = _instruction_text(relative_path)
        assert "do NOT produce both;" in text
        assert "redundant, disjointed" in text
        assert "one coherent" in text
