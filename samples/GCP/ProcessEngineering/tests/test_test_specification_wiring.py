"""Wiring coverage for the Test Specification feature: a new agent reads
whichever of a saved requirements summary, design document, and cloud
architecture diagram are present, generates test cases validating them
(with traceability and a coverage gap analysis), and persists the result
-- mirroring Requirements_Summary_Agent's own shape exactly, including
the chunked map-reduce path for large combined source material (see
Test_Case_Chunk_Generator_Agent, the sibling of Requirements_Chunk_
Extractor_Agent). Test_Consultant_Agent and Test_Reviewer_Agent mirror
Requirements_Consultant_Agent/Requirements_Reviewer_Agent respectively.
Mirrors the sibling Neuro-San port's own test_test_specification_wiring.py.
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


def _spec_agent_text() -> str:
    return _instruction_text("common/test_specification_agent.txt")


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
        assert "do NOT fabricate test cases with nothing to ground them in" in text

    def test_does_not_render_a_document_itself(self):
        # Standalone, save-only shape mirroring Requirements_Summary_Agent --
        # rendering is deferred to a separate, later request through the
        # generic Create_Doc_Agent/schema_type mechanism.
        text = _spec_agent_text()
        assert "create_standard_doc_from_file" not in text
        assert "can be rendered as a document or reviewed for quality on request" in text


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


class TestRootAgentWiring:
    def test_all_three_new_agents_are_in_root_agent_sub_agents(self):
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Test_Specification_Agent" in names
        assert "Test_Consultant_Agent" in names
        assert "Test_Reviewer_Agent" in names

    def test_chunk_generator_is_not_a_root_sub_agent(self):
        # Only ever called via AgentTool from Test_Specification_Agent,
        # same convention as Requirements_Chunk_Extractor_Agent.
        from process_agents.common.agent import root_agent

        names = [a.name for a in root_agent.sub_agents]
        assert "Test_Case_Chunk_Generator_Agent" not in names


class TestRouterInstructions:
    def test_router_references_all_three_new_agents(self):
        text = _router_text()
        assert "Test_Specification_Agent" in text
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

    def test_router_multi_intent_priority_mentions_all_three_new_agents(self):
        text = _router_text()
        assert "test specification validating the saved requirements/design/cloud architecture → Test_Specification_Agent" in text
        assert "saved test specification → Test_Consultant_Agent" in text
        assert "test specification quality → Test_Reviewer_Agent" in text

    def test_document_regeneration_section_names_the_test_specification(self):
        text = _router_text()
        assert "Regenerate the test specification document" in text

    def test_doc_generation_agent_recognizes_the_new_schema_type(self):
        text = _instruction_text("common/doc_generation_agent.txt")
        assert 'schema_type="test_specification"' in text
