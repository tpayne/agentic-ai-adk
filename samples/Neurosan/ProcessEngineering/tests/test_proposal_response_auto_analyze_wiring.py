"""Wiring coverage for live-testing fixes found after the Proposal-Response
Consultant/Reviewer work landed: proposal_response_pipeline.hocon's own
Ensure_Requirements_Summary_Agent (auto-analyzes a directory of RFP/
proposal files when no requirements summary is saved yet, instead of
requiring a separate Section 7 request first), and the router fix
removing 1d's self-contradiction with Section 7 ("review these documents
and create a requirements management document" never rendered a document
because 1d's own text said it excluded directory-based requests while
Section 7's own precedence rule said combined requests belong to
Section 1). Mirrors the sibling ADK port's own
test_ensure_requirements_summary_wiring.py.

The auto-analyze logic originally lived inline in Proposal_Response_
Pipeline's own single turn, alongside its already-long ~40-field drafting
instructions -- confirmed directly against a real test run to be too much
for one turn to execute reliably: the agent narrated a confident,
detailed "document generated" success story (a specific plausible
filename, compliance stats) while save_proposal_response/
regenerate_document were never actually called (no proposal_response.json
or matching .docx ever existed on disk, and the very next turn's
load_proposal_response call returned NOT_FOUND). Split into its own
separate agent-tool call (Ensure_Requirements_Summary_Agent) to keep each
turn's own tool-call burden smaller and more reliable, plus added a
mandatory STEP 3B re-load verification before the pipeline is allowed to
claim success in its own final reply -- defense in depth against the same
failure mode recurring for any other reason.
"""

from pathlib import Path

from coded_tools.requirements_summary.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as CanonicalLoadDirectoryContext,
)
from coded_tools.proposal_response_pipeline.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as PipelineLoadDirectoryContext,
)
from coded_tools.requirements_summary.save_requirements_summary_tool import (
    SaveRequirementsSummaryCodedTool as CanonicalSaveRequirementsSummary,
)
from coded_tools.proposal_response_pipeline.save_requirements_summary_tool import (
    SaveRequirementsSummaryCodedTool as PipelineSaveRequirementsSummary,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"
PIPELINE_HOCON = PROJECT_ROOT / "registries" / "proposal_response_pipeline.hocon"


def test_shims_reexport_the_canonical_tool_classes():
    assert PipelineLoadDirectoryContext is CanonicalLoadDirectoryContext
    assert PipelineSaveRequirementsSummary is CanonicalSaveRequirementsSummary


def test_pipeline_tools_array_includes_the_new_tools():
    text = PIPELINE_HOCON.read_text(encoding="utf-8")
    assert '"load_directory_context"' in text
    assert '"save_requirements_summary"' in text


def test_pipeline_delegates_to_a_separate_ensure_requirements_summary_agent():
    text = PIPELINE_HOCON.read_text(encoding="utf-8")
    assert '"name": "Ensure_Requirements_Summary_Agent"' in text
    assert '"tools": ["Ensure_Requirements_Summary_Agent", "load_requirements_summary", "load_proposal_response", "save_proposal_response", "regenerate_document"]' in text


def test_ensure_requirements_summary_agent_includes_the_mandatory_self_check():
    text = PIPELINE_HOCON.read_text(encoding="utf-8")
    assert "SCOPE CHECK" in text
    assert "RISKS CHECK" in text


def test_pipeline_has_a_mandatory_post_save_verification_step():
    # Direct fix for the confirmed fabricated-success bug: a long drafting
    # turn claimed a document was generated when save_proposal_response/
    # regenerate_document were never actually called.
    text = PIPELINE_HOCON.read_text(encoding="utf-8")
    assert "STEP 3B: VERIFY THE SAVE ACTUALLY PERSISTED" in text
    assert "do NOT claim in STEP 5 that a response was" in text
    assert "fabricated success" in text


def test_router_1d_no_longer_excludes_directory_based_requests():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "### 1d. REQUIREMENTS DOCUMENT CREATION (FROM A DESCRIPTION OR FROM FILES)" in text
    assert "NOT from reading a directory of existing source files" not in text


def test_router_1d_example_covers_the_review_and_create_phrasing():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "Review the documents in ./rfp-docs and create a requirements management document." in text


def test_directory_context_note_now_lists_1d_and_1e():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "(1a/1b/1c/1d/1e above, or the cloud diagram case in Section 6 below)" in text


def test_router_1e_example_covers_the_combined_analyze_and_draft_phrasing():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "no prior Section 7 run -- the pipeline analyzes ./rfp-docs itself first" in text


def test_router_routes_standalone_update_requests_to_the_reviewers_not_consultants():
    # Confirmed live bug: "Update the requirements summary so NFR-006 has a
    # status of needs rework... and tell me exactly what you changed" (no
    # "review" wording at all) was routed to the READ-ONLY
    # Requirements_Consultant_Agent, which replied "I cannot directly
    # update... I am a read-only consultant" instead of applying the fix.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "STANDALONE UPDATE REQUESTS (no \"review\" wording at all" in text
    assert "update the requirements summary so NFR-006 has a status of needs\nrework" in text
    assert "update the pricing approach to say all figures are TBD pending" in text
    assert text.count("READ-ONLY and has no tool to apply any change at all") == 2


def test_router_routes_clarifying_question_followups_back_to_the_originating_domain():
    # Confirmed live bug: "Create a requirements document." correctly
    # triggered a clarifying question, but the user's own follow-up answer
    # describing the system was then evaluated as a FRESH, standalone
    # request (no "requirements"/"process" signal words of its own) and
    # misrouted to the DESIGN DOCUMENT domain -- which then failed its own
    # document_type schema validation trying to build a document nobody
    # asked for.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "# FOLLOW-UP TO YOUR OWN CLARIFYING QUESTION (CONVERSATION CONTINUITY)" in text
    assert "patient referral\nscheduling system for a mid-sized dental clinic chain" in text
    assert "misrouted to the DESIGN DOCUMENT domain" in text


def test_domain_disambiguation_covers_all_five_domains_not_just_three():
    # Confirmed live bug (A7): "Can you take a look at this and tell me what
    # you think?" (no domain word at all) silently defaulted to "the most
    # recently discussed artifact" instead of asking a clarification
    # question. Root cause: the Domain Disambiguation section and Rule 10
    # only ever covered 2-3 of the system's actual 5 domains, so a bare
    # "this"/"it" had nowhere safe to fall through to.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert (
        "# DOMAIN DISAMBIGUATION (PROCESS vs. DESIGN DOCUMENT vs. CLOUD ARCHITECTURE DIAGRAM vs.\n"
        "# REQUIREMENTS SUMMARY vs. PROPOSAL RESPONSE)"
    ) in text
    assert "Signal words for a REQUIREMENTS SUMMARY:" in text
    assert "Signal words for a PROPOSAL RESPONSE:" in text


def test_rule_10_ambiguous_intent_rejects_recency_based_defaulting():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "## 10. AMBIGUOUS OR UNCLEAR INTENT" in text
    assert "EVEN IF something happens to be the\nmost recently saved/discussed artifact" in text
    assert "guessing which one based on recency is still guessing" in text


def test_router_never_continues_acting_after_its_single_tool_call_returns():
    # Confirmed live bug, far more severe than the fabrication bug above: a single human message,
    # "Create a requirements document.", correctly triggered a clarifying question -- and from
    # that point on, with ZERO further human input, the router invented and executed an entire
    # autonomous chain of roughly a dozen fabricated follow-up requests against real sub-agents
    # (a self-written project description, review/fix calls, document regenerations, a proposal
    # response for a scenario nobody asked for, and a self-issued process-creation request drawn
    # from this router's own sample_queries text), ending in a genuine pipeline-lock conflict
    # between two of its own self-issued calls. Real files were written and real cost was spent.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "# NEVER CONTINUE ACTING AFTER YOUR SINGLE TOOL CALL RETURNS (NO SELF-DRIVEN CASCADES)" in text
    assert "workflow for onboarding new dental clinics into the chain." in text
    assert "clearing that lock and retrying" in text
    assert "EXACTLY one tool call per incoming human message, full stop, never more than one" in text


def test_pipeline_requires_one_compliance_matrix_entry_per_requirement_including_goals_and_constraints():
    # Confirmed live bug: a 16-item requirements_register (including GOAL-001, CON-001, CON-002)
    # produced a compliance_matrix with only 10 entries -- GOAL/CON items were silently dropped
    # entirely, while the final reply still claimed full 16-requirement coverage. CON-001 (UK data
    # residency) and NFR-006 (the known RPO/backup conflict) were among the silently dropped items
    # -- the two most consequential entries in the whole register.
    text = PIPELINE_HOCON.read_text(encoding="utf-8")
    assert "NO EXCEPTIONS" in text
    assert "CONFIRMED PRODUCTION BUG: a 16-item requirements_register" in text
    assert "GOAL-001, NFR-002, NFR-005, NFR-006, CON-001, and CON-002 were all silently dropped entirely," in text


def test_router_never_fabricates_plain_consultant_qa_either():
    # Confirmed live bug: four consecutive plain read-only questions about a saved proposal
    # response ("What's in the saved proposal response?", compliance status, pricing, open
    # questions) were ALL answered directly by the router from memory of the drafting pipeline's
    # own earlier narrative, with ZERO calls to Proposal_Response_Consultant_Agent -- broadening
    # the fabrication bug beyond the "fix after a read-only review" case to plain Q&A as well. One
    # of the four fabricated answers even duplicated its own text within a single reply.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert text.count("EVERY SINGLE query") == 2
    assert "CONFIRMED PRODUCTION BUG: four consecutive plain questions" in text
    assert "duplicated its entire own text within itself" in text
    assert "What open questions or unaddressed items were flagged for the client?" in text


def test_4f_follow_up_confirmation_notes_the_partial_regression():
    # After the first round of this fix landed, a later re-test STILL showed 2 of 4 consecutive
    # consultant queries answered directly without calling the tool -- an improvement, but proof
    # the instruction alone doesn't fully eliminate this probabilistic LLM-compliance failure.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "FOLLOW-UP CONFIRMATION: after the above fix was first applied" in text
    assert "two of" in text
    assert "no amount of relevant context already sitting in your" in text


def test_router_never_fabricates_a_fix_apply_response_without_calling_the_tool():
    # Confirmed live bug, observed twice in the same test run: a "review ... for quality and fix
    # any issues" request immediately following a read-only "review ... for quality" request was
    # answered directly by the router itself -- a complete, convincing "fix applied" narrative
    # (including invented new requirement IDs FR-001a/FR-001b) with NO call to
    # Requirements_Reviewer_Agent/Proposal_Response_Reviewer_Agent at all. The subsequent document
    # regeneration proved nothing was ever persisted.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "# NEVER SYNTHESIZE A TOOL'S RESULT YOURSELF (NO FABRICATED FIX/APPLY RESPONSES)" in text
    assert "FR-001a/FR-001b" in text
    assert "no tool_start/tool_end entry exists for that turn in the" in text
    assert text.count("is a confirmed production bug, not a shortcut.") == 2
