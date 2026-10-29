"""Wiring coverage for registries/requirements_doc_pipeline.hocon -- the
CREATION counterpart to requirements_summary.hocon: synthesizes a brand-new
requirements register directly from a user's own description (no directory,
no already-saved summary required) and renders it as the final document in
one call. Fixes a real routing gap: a request like "create a requirements
document for a new drug ... based on US/UK standards ..." previously had no
requirements-domain creation path at all, so the router's generic "create a
... document" matching fell through to Design_Doc_Pipeline instead.
"""

from pathlib import Path

from coded_tools.regenerate_document.doc_generation_tool import (
    RegenerateDocumentCodedTool as CanonicalRegenerateDocument,
)
from coded_tools.requirements_doc_pipeline.doc_generation_tool import (
    RegenerateDocumentCodedTool as PipelineRegenerateDocument,
)
from coded_tools.requirements_summary.save_requirements_summary_tool import (
    SaveRequirementsSummaryCodedTool as CanonicalSaveRequirementsSummary,
)
from coded_tools.requirements_doc_pipeline.save_requirements_summary_tool import (
    SaveRequirementsSummaryCodedTool as PipelineSaveRequirementsSummary,
)
from coded_tools.requirements_summary.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as CanonicalLoadDirectoryContext,
)
from coded_tools.requirements_doc_pipeline.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as PipelineLoadDirectoryContext,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_HOCON = PROJECT_ROOT / "registries" / "manifest.hocon"
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"


def test_shims_reexport_the_canonical_tool_classes():
    assert PipelineRegenerateDocument is CanonicalRegenerateDocument
    assert PipelineSaveRequirementsSummary is CanonicalSaveRequirementsSummary
    assert PipelineLoadDirectoryContext is CanonicalLoadDirectoryContext


def test_manifest_registers_the_new_network():
    text = MANIFEST_HOCON.read_text(encoding="utf-8")
    assert '"requirements_doc_pipeline.hocon"' in text


def test_router_references_the_new_network():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "Requirements_Doc_Pipeline" in text
    assert '"/requirements_doc_pipeline"' in text


def test_router_1d_is_distinct_from_file_based_summarization_and_regeneration():
    # The real bug: no requirements-domain creation path existed at all, so
    # "create a requirements document" (no directory, no saved summary)
    # fell through to Design_Doc_Pipeline. Lock in that 1d exists and
    # explicitly distinguishes itself from both Section 7 (file-based,
    # never renders a document) and Section 9 (regenerates an EXISTING
    # summary only).
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "### 1d. REQUIREMENTS DOCUMENT CREATION (FROM A DESCRIPTION)" in text
    assert "is 1d (Requirements_Doc_Pipeline), not this section" in text


def test_multi_intent_priority_mentions_the_new_pipeline():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "requirements document from a description -> Requirements_Doc_Pipeline" in text
