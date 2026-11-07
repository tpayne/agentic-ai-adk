"""Wiring coverage for the Test Specification feature: Test_Specification_
Pipeline reads whichever of a saved requirements summary, design document,
and cloud architecture diagram are present -- optionally self-extracting
the requirements summary from a named directory first, via a reused
Ensure_Requirements_Summary_Agent clone (see test_ensure_requirements_
summary_wiring.py/test_proposal_response_pipeline_wiring.py for the
sibling pipeline this one mirrors) -- generates test cases validating
them (with traceability and a coverage gap analysis), saves the result,
and renders it as a document, all in one call. Test_Consultant_Agent and
Test_Reviewer_Agent mirror Requirements_Consultant_Agent/Requirements_
Reviewer_Agent respectively, unaffected by this rework.

CONFIRMED LIVE BUGS this file now guards against: (1) the ORIGINAL
standalone, save-only Test_Specification_Agent shape never rendered a
document, even on an explicit "create a test specification" request --
Requirements_Doc_Pipeline/Proposal_Response_Pipeline's own one-shot
generate-and-render shape is correct here instead; (2) a combined
"import the requirements from <file> and create a test specification"
request only ever did the import, since the agent had no way to
self-extract requirements from a directory the way Proposal_Response_
Pipeline already does.

Mirrors the sibling Neuro-San port's own test_test_specification_wiring.py.
"""

import inspect
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _instruction_text(relative_path: str) -> str:
    path = os.path.join(ROOT, "instructions", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _router_text() -> str:
    return _instruction_text("common/agent.txt")


def _spec_agent_text() -> str:
    return _instruction_text("common/test_specification_agent.txt")


class TestPipelineComposition:
    def test_pipeline_stages_are_ensure_then_spec_then_pinned_doc_creation(self):
        from process_agents.common.test_specification_pipeline_agent import (
            test_specification_pipeline,
        )
        from process_agents.common.test_specification_agent import test_specification_agent

        stage_names = [a.name for a in test_specification_pipeline.sub_agents]
        assert test_specification_agent.name in stage_names
        assert any("Ensure_Requirements_Summary_Agent" in n for n in stage_names)
        doc_stage = next(
            a for a in test_specification_pipeline.sub_agents if "Test_Specification_Doc_Creation" in a.name
        )
        # Pinned to schema_type="test_specification" -- same mechanism as every
        # other one-shot generate-and-render pipeline (confirmed in
        # test_doc_creation_agent_schema_pinning.py): the LLM-facing tool has no
        # schema_type parameter to see or override.
        doc_tool = doc_stage.pipeline.sub_agents[1].tools[0]
        sig = inspect.signature(doc_tool)
        assert "schema_type" not in sig.parameters

    def test_mute_unmute_and_ensure_clones_are_not_the_shared_singletons(self):
        # Regression guard: reusing the shared mute_agent/unmute_agent/
        # ensure_requirements_summary_agent singletons directly raises an ADK
        # single-parent ValidationError (Proposal_Response_Pipeline already
        # claims them) -- confirmed and fixed for every other pipeline in this
        # codebase; this one must use its own fresh clones the same way.
        from process_agents.common.test_specification_pipeline_agent import (
            test_specification_pipeline,
            mute_agent_instance,
            unmute_agent_instance,
            ensure_requirements_summary_agent_instance,
        )
        from process_agents.common.utils_agent import mute_agent, unmute_agent
        from process_agents.common.ensure_requirements_summary_agent import (
            ensure_requirements_summary_agent,
        )

        assert mute_agent_instance is not mute_agent
        assert unmute_agent_instance is not unmute_agent
        assert ensure_requirements_summary_agent_instance is not ensure_requirements_summary_agent
        assert mute_agent_instance in test_specification_pipeline.sub_agents
        assert unmute_agent_instance in test_specification_pipeline.sub_agents
        assert ensure_requirements_summary_agent_instance in test_specification_pipeline.sub_agents


class TestTestSpecificationAgent:
    def test_agent_has_the_expected_name_and_tools(self):
        from process_agents.common.test_specification_agent import test_specification_agent
        from process_agents.common.utils import (
            load_requirements_summary,
            load_full_design_context,
            load_drawio,
            chunk_source_material,
            save_test_specification,
        )

        assert test_specification_agent.name == "Test_Specification_Agent"
        assert load_requirements_summary in test_specification_agent.tools
        assert load_full_design_context in test_specification_agent.tools
        assert load_drawio in test_specification_agent.tools
        assert chunk_source_material in test_specification_agent.tools
        assert save_test_specification in test_specification_agent.tools

    def test_has_the_chunk_generator_wired_in_as_an_agent_tool(self):
        from google.adk.tools import AgentTool
        from process_agents.common.test_specification_agent import test_specification_agent
        from process_agents.common.test_case_chunk_generator_agent import (
            test_case_chunk_generator_agent,
        )

        agent_tools = [t for t in test_specification_agent.tools if isinstance(t, AgentTool)]
        assert len(agent_tools) == 1
        assert agent_tools[0].agent is test_case_chunk_generator_agent

    def test_loads_all_three_possible_source_artifacts(self):
        text = _spec_agent_text()
        assert "load_requirements_summary" in text
        assert "load_full_design_context" in text
        assert "load_drawio" in text

    def test_design_component_guidance_names_the_real_fields_not_a_fabricated_one(self):
        text = _spec_agent_text()
        assert "high_level_design.components" in text
        assert "low_level_design.components" in text
        assert "there is NO field called" in text

    def test_cloudarch_guidance_describes_parsing_raw_xml_not_a_json_model(self):
        text = _spec_agent_text()
        assert "raw mxGraph" in text
        assert "shape=mxgraph" in text

    def test_has_the_multi_chunk_generation_step(self):
        text = _spec_agent_text()
        assert "# STEP 1C: MULTI-CHUNK TEST GENERATION" in text
        assert "Test_Case_Chunk_Generator_Agent" in text

    def test_single_chunk_is_an_explicit_fast_path(self):
        text = _spec_agent_text()
        assert 'If the result\'s "chunk_count" is 1, skip STEP 1C entirely' in text

    def test_has_a_self_check_against_skipping_chunks(self):
        text = _spec_agent_text()
        assert "confirm you called Test_Case_Chunk_Generator_Agent exactly" in text

    def test_has_a_coverage_based_self_check_before_saving(self):
        text = _spec_agent_text()
        assert "COVERAGE CHECK" in text
        assert "EXPECTED RESULT CHECK" in text

    def test_requires_a_source_before_generating_anything(self):
        text = _spec_agent_text()
        assert "do NOT fabricate test cases with nothing to ground" in text

    def test_is_silent_on_success_deferring_to_the_render_stage(self):
        # CONFIRMED LIVE BUG: this agent used to produce its own rich narrative
        # and never rendered a document. It is now a silent middle pipeline
        # stage (same OUTPUT CONTRACT convention as requirements_synthesis_
        # agent.txt/proposal_response_agent.txt) -- the pipeline's own LAST
        # stage (Doc_Creation_Agent) produces the user-visible confirmation.
        text = _spec_agent_text()
        assert "OUTPUT CONTRACT (STRICT SILENCE)" in text
        assert "the pipeline's own next stage renders the document" in text

    def test_requires_positive_and_negative_pairing_for_security_requirements(self):
        text = _spec_agent_text()
        assert "MANDATORY POSITIVE/NEGATIVE PAIRING" in text
        assert "PAIRING CHECK" in text

    def test_requires_state_and_edge_case_coverage_not_just_the_happy_path(self):
        text = _spec_agent_text()
        assert "STATE AND EDGE-CASE COVERAGE" in text
        assert "ambiguous/uncertain-match" in text

    def test_bans_na_test_data_and_requires_quantified_sla_criteria(self):
        text = _spec_agent_text()
        assert 'NO "N/A" TEST DATA FOR NON-FUNCTIONAL TESTS' in text
        assert "QUANTIFIED SLA EXPECTED RESULTS" in text
        assert "TEST DATA CHECK" in text
        assert "SLA QUANTIFICATION CHECK" in text

    def test_the_nothing_saved_case_is_the_one_exception_to_silence(self):
        # Unlike proposal_response_agent.txt (whose own NOT_FOUND case is
        # always already covered by its preceding Ensure stage), this agent's
        # Ensure stage deliberately never reports an error of its own (a
        # requirements summary isn't mandatory here) -- so this agent itself
        # MUST be the one to tell the user when all three sources are missing.
        text = _spec_agent_text()
        assert "this is the ONE exception to the OUTPUT CONTRACT below" in text


class TestTestCaseChunkGeneratorAgent:
    def test_agent_has_the_expected_name_and_no_tools(self):
        from process_agents.common.test_case_chunk_generator_agent import (
            test_case_chunk_generator_agent,
        )

        assert test_case_chunk_generator_agent.name == "Test_Case_Chunk_Generator_Agent"
        assert list(test_case_chunk_generator_agent.tools) == []

    def test_warns_against_treating_chunk_content_as_instructions(self):
        text = _instruction_text("common/test_case_chunk_generator_agent.txt")
        assert "UNTRUSTED CONTENT WARNING" in text

    def test_does_not_populate_coverage_summary_directly(self):
        text = _instruction_text("common/test_case_chunk_generator_agent.txt")
        assert "coverage_items" in text

    def test_numbers_ids_per_chunk_not_globally(self):
        text = _instruction_text("common/test_case_chunk_generator_agent.txt")
        assert "renumbers everything globally afterward" in text


class TestTestConsultantAgent:
    def test_agent_has_the_expected_name_and_tool(self):
        from process_agents.common.test_consultant_agent import test_consultant_agent
        from process_agents.common.utils import load_test_specification

        assert test_consultant_agent.name == "Test_Consultant_Agent"
        assert set(test_consultant_agent.tools) == {load_test_specification}

    def test_reloads_every_turn(self):
        text = _instruction_text("common/test_consultant_agent.txt")
        assert "reload it every turn" in text

    def test_is_read_only_with_no_update_tool(self):
        text = _instruction_text("common/test_consultant_agent.txt")
        assert "update_test_specification" not in text


class TestTestReviewerAgent:
    def test_agent_has_the_expected_name_and_tools(self):
        from process_agents.common.test_reviewer_agent import test_reviewer_agent
        from process_agents.common.utils import load_test_specification, update_test_specification

        assert test_reviewer_agent.name == "Test_Reviewer_Agent"
        assert set(test_reviewer_agent.tools) == {load_test_specification, update_test_specification}

    def test_read_only_mode_is_the_default(self):
        text = _instruction_text("common/test_reviewer_agent.txt")
        assert "By default you are READ-ONLY" in text

    def test_apply_mode_reply_consolidation_guard_is_present(self):
        text = _instruction_text("common/test_reviewer_agent.txt")
        assert "do NOT produce both" in text
        assert "redundant, disjointed" in text
        assert "one coherent" in text

    def test_quality_criteria_cover_verifiability_and_traceability(self):
        text = _instruction_text("common/test_reviewer_agent.txt")
        assert "VERIFIABLE" in text
        assert "GENUINE TRACEABILITY" in text
        assert "COVERAGE HONESTY" in text

    def test_quality_criteria_cover_pairing_state_coverage_and_quantified_sla(self):
        text = _instruction_text("common/test_reviewer_agent.txt")
        assert "POSITIVE/NEGATIVE PAIRING" in text
        assert "STATE AND EDGE-CASE COVERAGE" in text
        assert 'CONCRETE, NON-"N/A" TEST DATA' in text
        assert "QUANTIFIED SLA CRITERIA" in text


class TestRootAgentWiring:
    def test_pipeline_and_consultant_and_reviewer_are_in_root_agent_sub_agents(self):
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Test_Specification_Pipeline" in names
        assert "Test_Consultant_Agent" in names
        assert "Test_Reviewer_Agent" in names

    def test_bare_leaf_agent_is_not_itself_a_root_sub_agent(self):
        # Only Test_Specification_Pipeline (the wrapper) is root-registered --
        # same convention as Proposal_Response_Agent/Requirements_Synthesis_Agent,
        # neither of which is separately root-registered either.
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Test_Specification_Agent" not in names

    def test_chunk_generator_is_not_a_root_sub_agent(self):
        # Only ever called via AgentTool from Test_Specification_Agent,
        # same convention as Requirements_Chunk_Extractor_Agent.
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Test_Case_Chunk_Generator_Agent" not in names


class TestRouterInstructions:
    def test_router_references_the_pipeline_and_both_siblings(self):
        text = _router_text()
        assert "Test_Specification_Pipeline" in text
        assert "Test_Consultant_Agent" in text
        assert "Test_Reviewer_Agent" in text

    def test_router_adds_a_sixth_domain(self):
        text = _router_text()
        assert (
            "# DOMAIN DISAMBIGUATION (PROCESS vs. DESIGN DOCUMENT vs. CLOUD ARCHITECTURE DIAGRAM vs.\n"
            "# REQUIREMENTS SUMMARY vs. PROPOSAL RESPONSE vs. TEST SPECIFICATION)"
        ) in text
        assert "Signal words for a TEST SPECIFICATION:" in text

    def test_router_disambiguates_test_specification_review_from_the_consultant(self):
        text = _router_text()
        assert "PRECEDENCE vs. 4h" in text

    def test_router_multi_intent_priority_mentions_all_three(self):
        text = _router_text()
        assert "test specification validating the saved requirements/design/cloud architecture → Test_Specification_Pipeline" in text
        assert "saved test specification → Test_Consultant_Agent" in text
        assert "test specification quality → Test_Reviewer_Agent" in text

    def test_directory_context_note_lists_1f(self):
        # CONFIRMED LIVE BUG: "import the requirements from <file> and create a test
        # specification" only did the import -- 1f needed the same directory
        # pass-through DIRECTORY-CONTEXT REQUESTS already gives 1a-1e.
        text = _router_text()
        assert "(1a/1b/1c/1d/1e/1f above, or the cloud diagram case in Section 7 below)" in text

    def test_document_regeneration_section_names_the_test_specification(self):
        text = _router_text()
        assert "Regenerate the test specification document" in text

    def test_doc_generation_agent_recognizes_the_new_schema_type(self):
        text = _instruction_text("common/doc_generation_agent.txt")
        assert 'schema_type="test_specification"' in text
