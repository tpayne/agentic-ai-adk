"""Wiring coverage for the two new standalone, on-demand proposal-response
networks: registries/proposal_response_consultant.hocon (narrative Q&A
over a saved proposal response) and registries/proposal_response_reviewer.hocon
(quality audit, with an intent-gated update_proposal_response tool). Both
mirror registries/requirements_consultant.hocon/requirements_reviewer.hocon's
shape -- see test_requirements_reviewer_simulation_wiring.py for the
analogous requirements-side coverage.
"""

from pathlib import Path

from coded_tools.proposal_response_pipeline.load_proposal_response_tool import (
    LoadProposalResponseCodedTool as CanonicalLoadProposalResponse,
)
from coded_tools.proposal_response_consultant.load_proposal_response_tool import (
    LoadProposalResponseCodedTool as ConsultantLoadProposalResponse,
)
from coded_tools.proposal_response_reviewer.load_proposal_response_tool import (
    LoadProposalResponseCodedTool as ReviewerLoadProposalResponse,
)
from coded_tools.proposal_response_pipeline.update_proposal_response_tool import (
    UpdateProposalResponseCodedTool as CanonicalUpdateProposalResponse,
)
from coded_tools.proposal_response_reviewer.update_proposal_response_tool import (
    UpdateProposalResponseCodedTool as ReviewerUpdateProposalResponse,
)
from coded_tools.requirements_summary.update_requirements_summary_tool import (
    UpdateRequirementsSummaryCodedTool as CanonicalUpdateRequirementsSummary,
)
from coded_tools.requirements_reviewer.update_requirements_summary_tool import (
    UpdateRequirementsSummaryCodedTool as ReviewerUpdateRequirementsSummary,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_HOCON = PROJECT_ROOT / "registries" / "manifest.hocon"
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"
REQUIREMENTS_REVIEWER_HOCON = PROJECT_ROOT / "registries" / "requirements_reviewer.hocon"
PROPOSAL_RESPONSE_REVIEWER_HOCON = PROJECT_ROOT / "registries" / "proposal_response_reviewer.hocon"


def test_shims_reexport_the_canonical_load_proposal_response_class():
    assert ConsultantLoadProposalResponse is CanonicalLoadProposalResponse
    assert ReviewerLoadProposalResponse is CanonicalLoadProposalResponse


def test_shims_reexport_the_canonical_update_classes():
    assert ReviewerUpdateProposalResponse is CanonicalUpdateProposalResponse
    assert ReviewerUpdateRequirementsSummary is CanonicalUpdateRequirementsSummary


def test_manifest_registers_both_new_networks():
    text = MANIFEST_HOCON.read_text(encoding="utf-8")
    assert '"proposal_response_consultant.hocon"' in text
    assert '"proposal_response_reviewer.hocon"' in text


def test_router_references_both_new_networks():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "Proposal_Response_Consultant_Agent" in text
    assert "Proposal_Response_Reviewer_Agent" in text
    assert '"/proposal_response_consultant"' in text
    assert '"/proposal_response_reviewer"' in text


def test_router_disambiguates_proposal_response_review_from_the_consultant():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "PRECEDENCE vs. 4f" in text


def test_router_mentions_review_and_fix_routes_to_the_same_agent():
    # Both reviewer agents are intent-gated (read-only by default, apply
    # fixes only when explicitly asked) -- the router must not split
    # "review and fix" into a separate pipeline.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert text.count("it is the SAME agent for both modes") == 2


def test_both_reviewer_networks_carry_the_intent_gated_apply_mode_instructions():
    for hocon_path in (REQUIREMENTS_REVIEWER_HOCON, PROPOSAL_RESPONSE_REVIEWER_HOCON):
        text = hocon_path.read_text(encoding="utf-8")
        assert "APPLY MODE" in text
        assert "By default you are READ-ONLY" in text or "By default I am read-only" in text
