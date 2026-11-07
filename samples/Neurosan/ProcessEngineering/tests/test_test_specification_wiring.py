"""Wiring coverage for the Test Specification feature: a new agent
network reads whichever of a saved requirements summary, design
document, and cloud architecture diagram are present, generates test
cases validating them (with traceability and a coverage gap analysis),
and persists/renders the result -- mirroring Requirements_Summary_Agent's
own shape exactly, including the chunked map-reduce path for large
combined source material (see Test_Case_Chunk_Generator_Agent, the
sibling of Requirements_Chunk_Extractor_Agent). Test_Consultant_Agent and
Test_Reviewer_Agent mirror Requirements_Consultant_Agent/Requirements_
Reviewer_Agent respectively.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_HOCON = PROJECT_ROOT / "registries" / "manifest.hocon"
TEST_SPECIFICATION_HOCON = PROJECT_ROOT / "registries" / "test_specification.hocon"
CHUNK_GENERATOR_HOCON = PROJECT_ROOT / "registries" / "test_case_chunk_generator.hocon"
TEST_CONSULTANT_HOCON = PROJECT_ROOT / "registries" / "test_consultant.hocon"
TEST_REVIEWER_HOCON = PROJECT_ROOT / "registries" / "test_reviewer.hocon"
PROCESS_ARCHITECT_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"


def test_manifest_registers_all_four_new_networks():
    text = MANIFEST_HOCON.read_text(encoding="utf-8")
    assert '"test_specification.hocon": true' in text
    assert '"test_case_chunk_generator.hocon": true' in text
    assert '"test_consultant.hocon": true' in text
    assert '"test_reviewer.hocon": true' in text


def test_router_actually_wires_the_three_reachable_networks_as_callable_tools():
    # CONFIRMED LIVE BUG: process_architect.hocon's own PROSE instructions (domain
    # disambiguation, Section 1f, 4h, 4i) mentioned "Test_Specification_Agent" /
    # "Test_Consultant_Agent" / "Test_Reviewer_Agent" by name, but the router's own
    # top-level "tools" array (the actual, live, callable wiring -- a SEPARATE thing
    # from the prose that describes when to use it) never got "/test_specification",
    # "/test_consultant", "/test_reviewer" added to it. Every live request was answered
    # with "I don't currently have a tool enabled..." -- the prose-only wiring tests in
    # this same file never caught it because they only ever checked for the AGENT NAME
    # string, not the "/network_file_name" tool reference the router actually calls.
    # Mirrors the pattern already present for /proposal_response_consultant and
    # /proposal_response_reviewer, which ARE correctly wired, confirming this was a
    # one-off omission in this phase's own router edit, not a systemic gap.
    text = PROCESS_ARCHITECT_HOCON.read_text(encoding="utf-8")
    # The file has TWO "tools": [ arrays -- the outer one wrapping every tool
    # definition block in this file, and the Process_Architect_Orchestrator's
    # OWN "tools" field (nested inside its own block, after its "instructions")
    # listing which of those blocks it can actually call. Anchor past the
    # orchestrator's own name to reach its own array, not the outer one.
    orchestrator_start = text.index('"name": "Process_Architect_Orchestrator"')
    tools_array_start = text.index('"tools": [', orchestrator_start)
    tools_array_text = text[tools_array_start: text.index("]", tools_array_start)]
    assert '"/test_specification"' in tools_array_text
    assert '"/test_consultant"' in tools_array_text
    assert '"/test_reviewer"' in tools_array_text


def test_chunk_generator_is_deliberately_not_a_top_level_router_tool():
    # The map-half network is only ever reached indirectly, as
    # Test_Specification_Agent's own sub-agent -- it must NOT appear in the
    # router's own top-level tools array (same convention as
    # /requirements_chunk_extractor).
    text = PROCESS_ARCHITECT_HOCON.read_text(encoding="utf-8")
    orchestrator_start = text.index('"name": "Process_Architect_Orchestrator"')
    tools_array_start = text.index('"tools": [', orchestrator_start)
    tools_array_text = text[tools_array_start: text.index("]", tools_array_start)]
    assert '"/test_case_chunk_generator"' not in tools_array_text
    assert '"/requirements_chunk_extractor"' not in tools_array_text


class TestTestSpecificationAgent:
    def test_agent_exists_with_the_expected_name(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert '"name": "Test_Specification_Pipeline"' in text

    def test_loads_all_three_possible_source_artifacts(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "load_requirements_summary" in text
        assert "load_full_design_context" in text or "design_json_tool" in text
        assert "load_drawio" in text

    def test_design_component_guidance_names_the_real_fields_not_a_fabricated_one(self):
        # Confirmed via direct research against design_json.py: there is NO
        # "architecture_components" field -- components live under
        # high_level_design.components / low_level_design.components. The
        # forbidden field name IS deliberately mentioned once, to warn the
        # LLM away from it -- this just confirms the real fields are named.
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "high_level_design.components" in text
        assert "low_level_design.components" in text
        assert "there is NO field called" in text

    def test_cloudarch_guidance_describes_parsing_raw_xml_not_a_json_model(self):
        # There is no cloudarch_data.json equivalent -- component identity
        # must be derived from the drawio XML's own value/style attributes.
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "raw mxGraph" in text
        assert "shape=mxgraph" in text

    def test_has_the_multi_chunk_generation_step(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "# STEP 1C: MULTI-CHUNK TEST GENERATION" in text
        assert "Test_Case_Chunk_Generator_Agent" in text

    def test_single_chunk_is_an_explicit_fast_path(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert 'If the result\'s "chunk_count" is 1, skip STEP 1C entirely' in text

    def test_has_a_self_check_against_skipping_chunks(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "confirm you called Test_Case_Chunk_Generator_Agent exactly" in text

    def test_has_a_coverage_based_self_check_before_saving(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "COVERAGE CHECK" in text
        assert "EXPECTED RESULT CHECK" in text

    def test_requires_a_source_before_generating_anything(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "do NOT fabricate test cases with nothing to ground them in" in text

    def test_tools_list_includes_the_chunk_generator_and_the_render_tool(self):
        # CONFIRMED LIVE BUG: this network originally mirrored Requirements_
        # Summary_Agent's own standalone, save-only shape (no render tool),
        # deferring document generation to a separate, later request. Live
        # testing showed this is the WRONG shape for test specifications --
        # a bare "create a test specification" request expects an actual
        # rendered document, same as Requirements_Doc_Pipeline/Proposal_
        # Response_Pipeline's own one-shot generate-and-render behavior.
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert '"/test_case_chunk_generator"' in text
        assert '"regenerate_document"' in text

    def test_has_the_render_document_step(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "# STEP 4: RENDER THE DOCUMENT (MANDATORY ON SUCCESS)" in text
        assert '"schema_type": "test_specification"' in text

    def test_has_the_ensure_requirements_pre_step_and_it_is_optional_not_mandatory(self):
        # CONFIRMED LIVE BUG: "import the requirements from <file> and create a test
        # specification" only ever did the import, dropping the test-specification
        # half of the request entirely -- Test_Specification_Pipeline had no way to
        # self-serve a directory-based requirements extraction the way Proposal_
        # Response_Pipeline already does via its own Ensure_Requirements_Summary_Agent.
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "# STEP 0: ENSURE A REQUIREMENTS SUMMARY WHEN A DIRECTORY IS NAMED" in text
        assert "Ensure_Requirements_Summary_Agent" in text
        # Unlike Proposal_Response_Pipeline's own identically-named helper, this one
        # must NEVER hard-stop the caller -- a design/cloudarch source is just as valid.
        assert "NEVER stops this pipeline or produces an\nerror of its own" in text

    def test_ensure_sub_agent_is_silent_and_never_blocks_on_a_missing_directory(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "OUTPUT CONTRACT (STRICT SILENCE)" in text
        assert 'output NOTHING and stop -- this is NOT an error' in text

    def test_requires_positive_and_negative_pairing_for_security_requirements(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "MANDATORY POSITIVE/NEGATIVE PAIRING" in text
        assert "PAIRING CHECK" in text

    def test_requires_state_and_edge_case_coverage_not_just_the_happy_path(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert "STATE AND EDGE-CASE COVERAGE" in text
        assert "ambiguous/uncertain-match" in text

    def test_bans_na_test_data_and_requires_quantified_sla_criteria(self):
        text = TEST_SPECIFICATION_HOCON.read_text(encoding="utf-8")
        assert 'NO "N/A" TEST DATA FOR NON-FUNCTIONAL TESTS' in text
        assert "QUANTIFIED SLA EXPECTED RESULTS" in text
        assert "TEST DATA CHECK" in text
        assert "SLA QUANTIFICATION CHECK" in text


class TestTestCaseChunkGeneratorAgent:
    def test_agent_exists_with_the_expected_name(self):
        text = CHUNK_GENERATOR_HOCON.read_text(encoding="utf-8")
        assert '"name": "Test_Case_Chunk_Generator_Agent"' in text

    def test_warns_against_treating_chunk_content_as_instructions(self):
        text = CHUNK_GENERATOR_HOCON.read_text(encoding="utf-8")
        assert "UNTRUSTED CONTENT WARNING" in text

    def test_does_not_populate_coverage_summary_directly(self):
        # The chunk generator reports coverage_items for the reduce step
        # to use -- it must not try to build the final coverage_summary
        # itself, since it only ever sees one chunk.
        text = CHUNK_GENERATOR_HOCON.read_text(encoding="utf-8")
        assert "coverage_items" in text

    def test_numbers_ids_per_chunk_not_globally(self):
        text = CHUNK_GENERATOR_HOCON.read_text(encoding="utf-8")
        assert "the reduce\n  step renumbers everything globally afterward" in text


class TestTestConsultantAgent:
    def test_agent_exists_with_the_expected_name(self):
        text = TEST_CONSULTANT_HOCON.read_text(encoding="utf-8")
        assert '"name": "Test_Consultant_Agent"' in text

    def test_reloads_every_turn(self):
        text = TEST_CONSULTANT_HOCON.read_text(encoding="utf-8")
        assert "reload it every turn" in text

    def test_is_read_only_with_no_update_tool(self):
        text = TEST_CONSULTANT_HOCON.read_text(encoding="utf-8")
        assert "update_test_specification" not in text


class TestTestReviewerAgent:
    def test_agent_exists_with_the_expected_name(self):
        text = TEST_REVIEWER_HOCON.read_text(encoding="utf-8")
        assert '"name": "Test_Reviewer_Agent"' in text

    def test_read_only_mode_is_the_default(self):
        text = TEST_REVIEWER_HOCON.read_text(encoding="utf-8")
        assert "By default you are READ-ONLY" in text

    def test_apply_mode_reply_consolidation_guard_is_present(self):
        # Mirrors the fix applied to every other reviewer this session:
        # one combined reply in apply mode, not two redundant blocks.
        text = TEST_REVIEWER_HOCON.read_text(encoding="utf-8")
        assert "do NOT produce both" in text
        assert "redundant, disjointed" in text
        assert "one coherent" in text

    def test_quality_criteria_cover_verifiability_and_traceability(self):
        text = TEST_REVIEWER_HOCON.read_text(encoding="utf-8")
        assert "VERIFIABLE" in text
        assert "GENUINE TRACEABILITY" in text
        assert "COVERAGE HONESTY" in text

    def test_quality_criteria_cover_pairing_state_coverage_and_quantified_sla(self):
        text = TEST_REVIEWER_HOCON.read_text(encoding="utf-8")
        assert "POSITIVE/NEGATIVE PAIRING" in text
        assert "STATE AND EDGE-CASE COVERAGE" in text
        assert 'CONCRETE, NON-"N/A" TEST DATA' in text
        assert "QUANTIFIED SLA CRITERIA" in text
