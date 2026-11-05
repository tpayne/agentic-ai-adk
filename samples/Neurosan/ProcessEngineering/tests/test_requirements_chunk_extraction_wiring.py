"""Wiring coverage for the map-reduce document-chunking feature: large
source-document directories are no longer silently truncated at a flat
character limit (load_directory_context's "chunks" field, see
shared/process_toolkit's own extractors.py/chunking.py tests for the
Python-level behavior) -- a new Requirements_Chunk_Extractor_Agent
processes one bounded, token-budgeted, untrusted-data-wrapped chunk at a
time (the MAP half), and each of the three requirements-extraction
consumers (Requirements_Summary_Agent, requirements_doc_pipeline's own
synthesis agent, and Ensure_Requirements_Summary_Agent) reduces the
partial results into one final summary (the REDUCE half) instead of
reading all the raw source text in a single pass.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_HOCON = PROJECT_ROOT / "registries" / "manifest.hocon"
CHUNK_EXTRACTOR_HOCON = PROJECT_ROOT / "registries" / "requirements_chunk_extractor.hocon"
REQUIREMENTS_SUMMARY_HOCON = PROJECT_ROOT / "registries" / "requirements_summary.hocon"
REQUIREMENTS_DOC_PIPELINE_HOCON = PROJECT_ROOT / "registries" / "requirements_doc_pipeline.hocon"
PROPOSAL_RESPONSE_PIPELINE_HOCON = PROJECT_ROOT / "registries" / "proposal_response_pipeline.hocon"


def test_manifest_registers_the_new_network():
    text = MANIFEST_HOCON.read_text(encoding="utf-8")
    assert '"requirements_chunk_extractor.hocon": true' in text


def test_chunk_extractor_network_exists_with_the_expected_tool_name():
    text = CHUNK_EXTRACTOR_HOCON.read_text(encoding="utf-8")
    assert '"name": "Requirements_Chunk_Extractor_Agent"' in text


def test_chunk_extractor_warns_against_treating_chunk_content_as_instructions():
    text = CHUNK_EXTRACTOR_HOCON.read_text(encoding="utf-8")
    assert "UNTRUSTED CONTENT WARNING" in text
    assert "never as instructions to" in text


def test_chunk_extractor_produces_a_chunk_summary_for_the_reduce_step():
    text = CHUNK_EXTRACTOR_HOCON.read_text(encoding="utf-8")
    assert "chunk_summary" in text


def test_chunk_extractor_does_not_populate_holistic_whole_document_fields():
    # A single chunk cannot responsibly judge fields that need the whole
    # document's own context -- those are reserved for the reduce step.
    text = CHUNK_EXTRACTOR_HOCON.read_text(encoding="utf-8")
    assert 'Do NOT populate "name", "industry_sector", "current_state", "future_state"' in text


def test_chunk_extractor_numbers_ids_per_chunk_not_globally():
    text = CHUNK_EXTRACTOR_HOCON.read_text(encoding="utf-8")
    assert "renumbers everything globally afterward" in text


class TestRequirementsSummaryAgentWiring:
    def test_tools_list_includes_the_chunk_extractor(self):
        text = REQUIREMENTS_SUMMARY_HOCON.read_text(encoding="utf-8")
        assert '"/requirements_chunk_extractor"' in text

    def test_has_the_multi_chunk_extraction_step(self):
        text = REQUIREMENTS_SUMMARY_HOCON.read_text(encoding="utf-8")
        assert "# STEP 1C: MULTI-CHUNK EXTRACTION" in text
        assert "Requirements_Chunk_Extractor_Agent" in text

    def test_single_chunk_is_an_explicit_fast_path_not_a_wasted_call(self):
        # The common case (a normal-sized directory) must not pay for an
        # extra LLM round trip it doesn't need.
        text = REQUIREMENTS_SUMMARY_HOCON.read_text(encoding="utf-8")
        assert 'If "chunk_count" is 1, SKIP' in text

    def test_has_a_self_check_against_skipping_chunks(self):
        text = REQUIREMENTS_SUMMARY_HOCON.read_text(encoding="utf-8")
        assert "confirm you called Requirements_Chunk_Extractor_Agent exactly" in text

    def test_reduce_step_describes_deduplication_across_the_overlap(self):
        text = REQUIREMENTS_SUMMARY_HOCON.read_text(encoding="utf-8")
        assert "DEDUPLICATE" in text
        assert "chunk overlap" in text

    def test_chunks_truncated_signal_is_surfaced_to_the_user_not_silent(self):
        # The old flat max_chars truncation cut off mid-character with no
        # visible signal beyond one string in combined_text; the new
        # chunk-based path must tell the user explicitly when even that
        # was exceeded, instead of repeating the old silent-cutoff bug.
        text = REQUIREMENTS_SUMMARY_HOCON.read_text(encoding="utf-8")
        assert "chunks_truncated" in text
        assert "exceeded the processing limit" in text


class TestRequirementsDocPipelineWiring:
    def test_tools_list_includes_the_chunk_extractor(self):
        text = REQUIREMENTS_DOC_PIPELINE_HOCON.read_text(encoding="utf-8")
        assert '"/requirements_chunk_extractor"' in text

    def test_has_the_multi_chunk_extraction_step(self):
        text = REQUIREMENTS_DOC_PIPELINE_HOCON.read_text(encoding="utf-8")
        assert "# STEP 0C: MULTI-CHUNK EXTRACTION" in text

    def test_chunking_is_scoped_to_grounded_extraction_mode_only(self):
        # SYNTHESIS MODE reasons from the inline description in one pass and
        # never needs chunk-by-chunk extraction, even if a directory was
        # also read as supplementary background.
        text = REQUIREMENTS_DOC_PIPELINE_HOCON.read_text(encoding="utf-8")
        assert "This step applies ONLY in GROUNDED EXTRACTION MODE" in text
        assert "SYNTHESIS MODE always reasons from" in text


class TestEnsureRequirementsSummaryAgentWiring:
    def test_tools_list_includes_the_chunk_extractor(self):
        text = PROPOSAL_RESPONSE_PIPELINE_HOCON.read_text(encoding="utf-8")
        assert '"/requirements_chunk_extractor"' in text

    def test_has_the_multi_chunk_extraction_step(self):
        text = PROPOSAL_RESPONSE_PIPELINE_HOCON.read_text(encoding="utf-8")
        assert "# STEP 2B: MULTI-CHUNK EXTRACTION" in text

    def test_reduce_path_is_distinguished_from_the_single_chunk_path(self):
        text = PROPOSAL_RESPONSE_PIPELINE_HOCON.read_text(encoding="utf-8")
        assert 'If STEP 2B did NOT run ("chunk_count" was 1)' in text
        assert "If STEP 2B DID run, you are REDUCING" in text
