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
    def test_agent_has_the_four_expected_tools(self):
        from google.adk.tools import AgentTool
        from process_agents.common.ensure_requirements_summary_agent import (
            ensure_requirements_summary_agent,
        )
        from process_agents.common.requirements_chunk_extractor_agent import (
            requirements_chunk_extractor_agent,
        )
        from process_agents.common.utils import (
            load_requirements_summary,
            load_directory_context,
            save_requirements_summary,
        )

        plain_tools = {
            t for t in ensure_requirements_summary_agent.tools if not isinstance(t, AgentTool)
        }
        assert plain_tools == {
            load_requirements_summary,
            load_directory_context,
            save_requirements_summary,
        }
        agent_tools = [
            t for t in ensure_requirements_summary_agent.tools if isinstance(t, AgentTool)
        ]
        assert len(agent_tools) == 1
        assert agent_tools[0].agent is requirements_chunk_extractor_agent

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


class TestRouterRoutesStandaloneUpdateRequestsToTheReviewers:
    # Confirmed live bug: "Update the requirements summary so NFR-006 has a
    # status of needs rework... and tell me exactly what you changed" (no
    # "review" wording at all) was routed to the READ-ONLY
    # Requirements_Consultant_Agent, which replied "I cannot directly
    # update... I am a read-only consultant" instead of applying the fix.
    def test_requirements_section_covers_standalone_update_requests(self):
        text = _router_text()
        assert "STANDALONE UPDATE REQUESTS (no \"review\" wording at all" in text
        assert "update the requirements summary so NFR-006 has a status of needs\nrework" in text

    def test_proposal_response_section_covers_standalone_update_requests(self):
        text = _router_text()
        assert "update the pricing approach to say all figures are TBD pending" in text

    def test_both_sections_warn_the_consultants_have_no_update_tool(self):
        text = _router_text()
        assert text.count("READ-ONLY and has no tool to apply any change at all") == 2


class TestRouterConversationContinuityAfterAClarifyingQuestion:
    # Confirmed live bug: "Create a requirements document." correctly
    # triggered a clarifying question, but the user's own follow-up answer
    # describing the system was then evaluated as a FRESH, standalone
    # request (no "requirements"/"process" signal words of its own) and
    # misrouted to the DESIGN DOCUMENT domain -- which then failed its own
    # document_type schema validation trying to build a document nobody
    # asked for.
    def test_router_has_the_continuity_section(self):
        text = _router_text()
        assert "# FOLLOW-UP TO YOUR OWN CLARIFYING QUESTION (CONVERSATION CONTINUITY)" in text

    def test_continuity_section_names_the_confirmed_bug(self):
        text = _router_text()
        assert "patient referral\nscheduling system for a mid-sized dental clinic chain" in text
        assert "misrouted to the DESIGN DOCUMENT domain" in text


class TestDomainDisambiguationCoversAllFiveDomains:
    # Confirmed live bug (A7): "Can you take a look at this and tell me what
    # you think?" (no domain word at all) silently defaulted to "the most
    # recently discussed artifact" instead of asking a clarification
    # question. Root cause: the Domain Disambiguation section and Rule 11
    # only ever covered 2-3 of the system's actual 5 domains, so a bare
    # "this"/"it" had nowhere safe to fall through to.
    def test_domain_disambiguation_header_lists_all_five_domains(self):
        # A sixth domain (TEST SPECIFICATION) was added later, in the same spot, under the same rule.
        text = _router_text()
        assert (
            "# DOMAIN DISAMBIGUATION (PROCESS vs. DESIGN DOCUMENT vs. CLOUD ARCHITECTURE DIAGRAM vs.\n"
            "# REQUIREMENTS SUMMARY vs. PROPOSAL RESPONSE vs. TEST SPECIFICATION)"
        ) in text
        assert "Signal words for a REQUIREMENTS SUMMARY:" in text
        assert "Signal words for a PROPOSAL RESPONSE:" in text
        assert "Signal words for a TEST SPECIFICATION:" in text

    def test_rule_11_ambiguous_intent_rejects_recency_based_defaulting(self):
        text = _router_text()
        assert "## 11. AMBIGUOUS OR UNCLEAR INTENT" in text
        assert "EVEN IF something happens to be the\nmost recently saved/discussed artifact" in text
        assert "guessing which one based on recency is still guessing" in text


class TestRouterNeverContinuesActingAfterItsSingleToolCallReturns:
    # Confirmed live bug on the sibling Neuro-San port, far more severe than the fabrication bug
    # below: a single human message, "Create a requirements document.", correctly triggered a
    # clarifying question -- and from that point on, with ZERO further human input, the router
    # invented and executed an entire autonomous chain of roughly a dozen fabricated follow-up
    # requests against real sub-agents, ending in a genuine pipeline-lock conflict between two of
    # its own self-issued calls. Real files were written and real cost was spent.
    def test_router_has_the_no_self_driven_cascades_section(self):
        text = _router_text()
        assert "# NEVER CONTINUE ACTING AFTER YOUR SINGLE TOOL CALL RETURNS (NO SELF-DRIVEN CASCADES)" in text
        assert "workflow for onboarding new dental clinics into the chain." in text
        assert "clearing that lock and retrying" in text

    def test_role_section_states_exactly_one_tool_call_per_message(self):
        text = _router_text()
        assert "EXACTLY one tool call per incoming human message, full stop, never\nmore than one" in text


class TestProposalResponseComplianceMatrixCompleteness:
    # Confirmed live bug on the sibling Neuro-San port: a 16-item requirements_register
    # (including GOAL-001, CON-001, CON-002) produced a compliance_matrix with only 10 entries --
    # GOAL/CON items were silently dropped entirely, while the final reply still claimed full
    # 16-requirement coverage. CON-001 (UK data residency) and NFR-006 (the known RPO/backup
    # conflict) were among the silently dropped items -- the two most consequential entries in
    # the whole register.
    def test_requires_one_entry_per_requirement_including_goals_and_constraints(self):
        text = _instruction_text("common/proposal_response_agent.txt")
        assert "NO EXCEPTIONS" in text
        assert "CONFIRMED PRODUCTION BUG (on the sibling Neuro-San port of this same agent)" in text
        assert "CON-001, and CON-002 were all silently dropped entirely, while the final reply" in text


class TestRouterNeverFabricatesPlainConsultantQAEither:
    # Confirmed live bug on the sibling Neuro-San port: four consecutive plain read-only questions
    # about a saved proposal response were ALL answered directly by the router from memory of the
    # drafting pipeline's own earlier narrative, with ZERO transfers to
    # Proposal_Response_Consultant_Agent -- broadening the fabrication bug beyond "fix after a
    # read-only review" to plain Q&A as well. One of the four fabricated answers even duplicated
    # its own text within a single reply.
    def test_4d_and_4f_both_require_a_transfer_for_every_query(self):
        # 2 from the original proposal-response fix (4d/4f) plus 1 more added later for the
        # test-specification domain's own analogous rule (4h).
        text = _router_text()
        assert text.count("EVERY SINGLE query") == 3

    def test_4f_names_the_confirmed_bug(self):
        text = _router_text()
        assert "four consecutive" in text
        assert "entire own text within itself" in text

    def test_4f_follow_up_confirmation_notes_the_partial_regression(self):
        # After the first round of this fix landed, a later re-test on the sibling Neuro-San port
        # STILL showed 2 of 4 consecutive consultant queries answered directly without calling the
        # tool -- an improvement, but proof the instruction alone doesn't fully eliminate this
        # probabilistic LLM-compliance failure.
        text = _router_text()
        assert "FOLLOW-UP CONFIRMATION (on the sibling Neuro-San port)" in text
        assert "two of four consecutive plain questions" in text


class TestRouterNeverFabricatesAFixApplyResponse:
    # Confirmed live bug on the sibling Neuro-San port, observed twice in the same test run: a
    # "review ... for quality and fix any issues" request immediately following a read-only
    # "review ... for quality" request was answered directly by the router itself -- a complete,
    # convincing "fix applied" narrative (including invented new requirement IDs
    # FR-001a/FR-001b) with NO call to Requirements_Reviewer_Agent/Proposal_Response_Reviewer_Agent
    # at all. The subsequent document regeneration proved nothing was ever persisted.
    def test_router_has_the_never_synthesize_section(self):
        text = _router_text()
        assert "# NEVER SYNTHESIZE A TOOL'S RESULT YOURSELF (NO FABRICATED FIX/APPLY RESPONSES)" in text
        assert "FR-001a/FR-001b" in text
        assert "no tool-call entry exists for that" in text

    def test_4e_and_4g_both_reinforce_the_rule(self):
        text = _router_text()
        assert text.count("is a confirmed production bug, not a shortcut.") == 2
