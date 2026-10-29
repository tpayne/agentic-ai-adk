"""Wiring coverage for the two new standalone, on-demand requirements
agents: Requirements_Reviewer_Agent (SRS/ISO-29148 quality audit of the
saved requirements) and Requirements_Simulation_Query_Agent (fresh
completeness/gap analysis beyond what extraction already flagged). Both
mirror requirements_consultant_agent.py's exact shape -- single tool, no
save/creation tool, no loop_control/iteration_feedback machinery --
deliberately NOT the CloudArch_Reviewer_Agent/Compliance_Agent pattern
(not a pipeline-internal auto-revision gate). Mirrors the sibling
neuro-san port's own test_requirements_reviewer_simulation_wiring.py.
"""

import os

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _instruction_text(relative_path: str) -> str:
    path = os.path.join(ROOT, "instructions", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _router_text() -> str:
    return _instruction_text("common/agent.txt")


class TestAgentsUseTheCanonicalLoadRequirementsSummaryTool:
    def test_reviewer_agent_tool_is_identical_to_the_consultants(self):
        from process_agents.common.requirements_consultant_agent import requirements_consultant_agent
        from process_agents.common.requirements_reviewer_agent import requirements_reviewer_agent
        from process_agents.common.utils import load_requirements_summary

        assert load_requirements_summary in requirements_consultant_agent.tools
        assert load_requirements_summary in requirements_reviewer_agent.tools

    def test_simulation_query_agent_tool_is_identical_to_the_consultants(self):
        from process_agents.common.requirements_consultant_agent import requirements_consultant_agent
        from process_agents.common.requirements_simulation_agent import requirements_simulation_query_agent
        from process_agents.common.utils import load_requirements_summary

        assert load_requirements_summary in requirements_consultant_agent.tools
        assert load_requirements_summary in requirements_simulation_query_agent.tools

    def test_neither_new_agent_has_a_save_or_loop_control_tool(self):
        from process_agents.common.requirements_reviewer_agent import requirements_reviewer_agent
        from process_agents.common.requirements_simulation_agent import requirements_simulation_query_agent

        assert len(requirements_reviewer_agent.tools) == 1
        assert len(requirements_simulation_query_agent.tools) == 1


class TestRootAgentWiring:
    def test_both_new_agents_are_in_root_agent_sub_agents(self):
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Requirements_Reviewer_Agent" in names
        assert "Requirements_Simulation_Query_Agent" in names


class TestRouterInstructions:
    def test_router_references_both_new_agents(self):
        text = _router_text()
        assert "Requirements_Reviewer_Agent" in text
        assert "Requirements_Simulation_Query_Agent" in text

    def test_router_disambiguates_review_from_the_existing_consultant(self):
        # The one real design risk in this feature: both new agents
        # overlap in phrasing with the existing Consultant. Lock in that
        # the precedence rule is actually present, not just implied.
        text = _router_text()
        assert text.count("PRECEDENCE vs. 4d") == 2  # once in 3f, once in 4e

    def test_router_multi_intent_priority_mentions_both_new_agents(self):
        text = _router_text()
        assert "requirements completeness → Requirements_Simulation_Query_Agent" in text
        assert "requirements quality → Requirements_Reviewer_Agent" in text

    def test_document_regeneration_section_mentions_requirements_document(self):
        text = _router_text()
        assert "Regenerate the requirements document" in text
