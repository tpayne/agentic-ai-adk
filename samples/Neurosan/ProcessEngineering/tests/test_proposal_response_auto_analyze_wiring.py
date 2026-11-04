"""Wiring coverage for live-testing fixes found after the Proposal-Response
Consultant/Reviewer work landed: proposal_response_pipeline.hocon's own
STEP 1A (auto-analyzes a directory of RFP/proposal files when no
requirements summary is saved yet, instead of requiring a separate
Section 7 request first), and the router fix removing 1d's self-
contradiction with Section 7 ("review these documents and create a
requirements management document" never rendered a document because 1d's
own text said it excluded directory-based requests while Section 7's own
precedence rule said combined requests belong to Section 1). Mirrors the
sibling ADK port's own test_ensure_requirements_summary_wiring.py.
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


def test_pipeline_has_the_auto_analyze_step():
    text = PIPELINE_HOCON.read_text(encoding="utf-8")
    assert "STEP 1A: ANALYZE REQUIREMENTS NOW IF NONE SAVED YET" in text
    assert "continue to STEP 1B in this SAME turn" in text


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
