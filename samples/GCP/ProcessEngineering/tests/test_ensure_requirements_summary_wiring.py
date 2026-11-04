"""Wiring coverage for live-testing fixes found after the Proposal-Response
Consultant/Reviewer work landed: Ensure_Requirements_Summary_Agent (the new
first stage of Proposal_Response_Pipeline that auto-analyzes a directory of
RFP/proposal files when no requirements summary is saved yet, instead of
requiring a separate Section 8 request first), and the router fix removing
1d's self-contradiction with Section 8 ("review these documents and create a
requirements management document" never rendered a document because 1d's own
text said it excluded directory-based requests while Section 8's own
precedence rule said combined requests belong to Section 1). Mirrors the
sibling neuro-san port's own equivalent coverage.
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


class TestEnsureRequirementsSummaryAgent:
    def test_agent_has_the_three_expected_tools(self):
        from process_agents.common.ensure_requirements_summary_agent import (
            ensure_requirements_summary_agent,
        )
        from process_agents.common.utils import (
            load_requirements_summary,
            load_directory_context,
            save_requirements_summary,
        )

        assert set(ensure_requirements_summary_agent.tools) == {
            load_requirements_summary,
            load_directory_context,
            save_requirements_summary,
        }

    def test_agent_is_the_first_stage_of_the_proposal_response_pipeline(self):
        from process_agents.common.proposal_response_pipeline_agent import proposal_response_pipeline
        from process_agents.common.ensure_requirements_summary_agent import (
            ensure_requirements_summary_agent,
        )
        from process_agents.common.proposal_response_agent import proposal_response_agent

        stage_names = [a.name for a in proposal_response_pipeline.sub_agents]
        assert ensure_requirements_summary_agent.name in stage_names
        assert stage_names.index(ensure_requirements_summary_agent.name) < stage_names.index(
            proposal_response_agent.name
        )


class TestRouter1dNoLongerContradictsSection8:
    def test_1d_header_covers_files_as_well_as_a_description(self):
        text = _router_text()
        assert "### 1d. REQUIREMENTS DOCUMENT CREATION (FROM A DESCRIPTION OR FROM FILES)" in text

    def test_1d_no_longer_excludes_directory_based_requests(self):
        text = _router_text()
        assert "NOT from reading a directory of existing source files" not in text

    def test_1d_example_covers_the_review_and_create_phrasing(self):
        text = _router_text()
        assert "Review the documents in ./rfp-docs and create a requirements management document." in text

    def test_directory_context_note_now_lists_1d_and_1e(self):
        text = _router_text()
        assert "(1a/1b/1c/1d/1e above, or the cloud diagram case in Section 7 below)" in text


class TestRouter1eNoLongerHardStops:
    def test_1e_describes_the_self_sufficient_pipeline(self):
        text = _router_text()
        assert "analyzing them itself first" in text

    def test_1e_example_covers_the_combined_analyze_and_draft_phrasing(self):
        text = _router_text()
        assert "no prior Section 8 run -- the pipeline analyzes ./rfp-docs itself first" in text


class TestMandatorySelfCheckBeforeSaving:
    # Instruction strengthening alone (self-check criteria embedded in
    # field descriptions) proved insufficient in live testing -- Scope
    # bullets stayed one-line and Risks stayed empty even after a server
    # restart. This locks in the follow-up fix: an explicit, mandatory
    # self-check step the agent must run and act on before saving,
    # across every path that drafts a requirements summary.
    def test_requirements_summary_agent_has_the_self_check_step(self):
        text = _instruction_text("common/requirements_summary_agent.txt")
        assert "STEP 2F: MANDATORY SELF-CHECK BEFORE SAVING" in text
        assert "SCOPE CHECK" in text
        assert "RISKS CHECK" in text

    def test_requirements_synthesis_agent_has_the_self_check_step(self):
        text = _instruction_text("common/requirements_synthesis_agent.txt")
        assert "STEP 2F: MANDATORY SELF-CHECK BEFORE SAVING" in text
        assert "SCOPE CHECK" in text
        assert "RISKS CHECK" in text

    def test_ensure_requirements_summary_agent_has_the_self_check_step(self):
        text = _instruction_text("common/ensure_requirements_summary_agent.txt")
        assert "STEP 3B: MANDATORY SELF-CHECK BEFORE SAVING" in text
        assert "SCOPE CHECK" in text
        assert "RISKS CHECK" in text


class TestProposalResponseAgentDefersMessagingToTheNewStage:
    def test_instructions_no_longer_tell_the_drafting_agent_to_speak_on_not_found(self):
        text = _instruction_text("common/proposal_response_agent.txt")
        assert "stay SILENT and STOP" in text
        assert "already told the user what's missing" in text
