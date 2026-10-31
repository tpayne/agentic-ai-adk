"""Wiring coverage for registries/proposal_response_pipeline.hocon --
drafts a formal Response to Proposal against an ALREADY-saved
requirements summary (an RFP/proposal's own analyzed requirements
register) plus a description of the responding organization's
solution/offering, and renders it as the final document in one call.
Modeled closely on requirements_doc_pipeline.hocon's own shape -- mirrors
the sibling ADK port's own test_proposal_response_pipeline_wiring.py.
"""

from pathlib import Path

from coded_tools.regenerate_document.doc_generation_tool import (
    RegenerateDocumentCodedTool as CanonicalRegenerateDocument,
)
from coded_tools.proposal_response_pipeline.doc_generation_tool import (
    RegenerateDocumentCodedTool as PipelineRegenerateDocument,
)
from coded_tools.requirements_summary.load_requirements_summary_tool import (
    LoadRequirementsSummaryCodedTool as CanonicalLoadRequirementsSummary,
)
from coded_tools.proposal_response_pipeline.load_requirements_summary_tool import (
    LoadRequirementsSummaryCodedTool as PipelineLoadRequirementsSummary,
)
from coded_tools.proposal_response_pipeline.save_proposal_response_tool import (
    SaveProposalResponseCodedTool,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_HOCON = PROJECT_ROOT / "registries" / "manifest.hocon"
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"


def test_shims_reexport_the_canonical_tool_classes():
    assert PipelineRegenerateDocument is CanonicalRegenerateDocument
    assert PipelineLoadRequirementsSummary is CanonicalLoadRequirementsSummary


def test_save_proposal_response_rejects_a_non_dict_response():
    tool = SaveProposalResponseCodedTool()
    result = tool.invoke({"response": "not a dict"}, {})
    assert result.startswith("ERROR:")


def test_manifest_registers_the_new_network():
    text = MANIFEST_HOCON.read_text(encoding="utf-8")
    assert '"proposal_response_pipeline.hocon"' in text


def test_router_references_the_new_network():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "Proposal_Response_Pipeline" in text
    assert '"/proposal_response_pipeline"' in text


def test_router_1e_exists_and_requires_a_saved_requirements_summary():
    # The real functional gap this feature closes: there is no
    # requirements-domain creation path for drafting a RESPONSE to
    # someone else's requirements -- 1e fills that in, with a hard
    # prerequisite (unlike 1a/1b/1d) that a requirements summary must
    # already exist.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "### 1e. PROPOSAL RESPONSE DOCUMENT CREATION" in text
    assert "this rule has a hard prerequisite" in text


def test_router_distinguishes_1e_from_1d():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "PRECEDENCE vs. 1d" in text


def test_section_1c_points_proposal_response_imports_to_the_new_pipeline():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "a proposal response to Proposal_Response_Pipeline" in text


def test_multi_intent_priority_mentions_the_new_pipeline():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "proposal response from an RFP's analyzed requirements -> Proposal_Response_Pipeline" in text


def test_document_regeneration_section_mentions_the_proposal_response_document():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "Regenerate the proposal response document" in text


def test_regenerate_document_hocon_supports_proposal_response_schema_type():
    regen_hocon = (PROJECT_ROOT / "registries" / "regenerate_document.hocon").read_text(encoding="utf-8")
    assert '"process", "design", "requirements", "proposal_response"' in regen_hocon
