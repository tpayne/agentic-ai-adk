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
