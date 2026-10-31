"""Regression coverage for the actual bug report: "a request to do a cloud
architecture gets contaminated with the process json" -- the same root
cause (an ambiguous process-or-design loader/generator that silently
prefers "process" whenever BOTH output/process_data.json and
output/design_data.json exist) also contaminated the design pipeline's
own final diagram/document-generation step, via Doc_Creation_Agent's
shared, unpinned Edge_Inference_Agent/Document_Generation_Agent clones.

build_edge_inference_instance/build_doc_generation_instance now accept an
optional schema_type: when given, the returned agent's own tool is
replaced with a zero-argument closure hardcoded to that domain -- the LLM
has no parameter to see or override. When omitted (Create_Doc_Agent's own
standalone "regenerate whichever document applies" case), the original,
LLM-settable tool is left in place.
"""

import inspect
import json
import os

import docx
import pytest

from process_toolkit import paths
from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME, DESIGN_JSON_FILENAME
from process_toolkit.requirements_summary.requirements_summary import REQUIREMENTS_SUMMARY_FILENAME
from process_toolkit.proposal_response.proposal_response import PROPOSAL_RESPONSE_FILENAME


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    os.makedirs("output", exist_ok=True)
    yield tmp_path


def _write_process_json():
    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"process_name": "Vendor Onboarding", "process_steps": []}, f)


def _write_design_json():
    with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"document_metadata": {"title": "Checkout Service", "system_name": "Checkout Service"}}, f)


def _write_requirements_summary_json():
    with open(paths.output_path(REQUIREMENTS_SUMMARY_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"industry_sector": "Healthcare", "requirements_register": []}, f)


def _write_proposal_response_json():
    with open(paths.output_path(PROPOSAL_RESPONSE_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"summary": "Our response.", "compliance_matrix": []}, f)


class TestEdgeInferencePinning:
    def test_pinned_process_tool_has_no_llm_visible_schema_type_parameter(self):
        from process_agents.common.doc_creation_agent import build_edge_inference_instance

        agent = build_edge_inference_instance("process")
        assert len(agent.tools) == 1
        sig = inspect.signature(agent.tools[0])
        assert "schema_type" not in sig.parameters

    def test_unpinned_build_leaves_the_original_llm_settable_tool(self):
        from process_agents.common.doc_creation_agent import build_edge_inference_instance
        from process_agents.common.edge_inference_agent import generate_clean_diagram

        agent = build_edge_inference_instance(None)
        assert generate_clean_diagram in agent.tools
        sig = inspect.signature(agent.tools[list(agent.tools).index(generate_clean_diagram)])
        assert "schema_type" in sig.parameters

    def test_pinned_process_tool_ignores_a_coexisting_design_document(self):
        from process_agents.common.doc_creation_agent import build_edge_inference_instance

        _write_process_json()
        _write_design_json()
        agent = build_edge_inference_instance("process")
        result = agent.tools[0]()

        assert "Diagram successfully generated at" in result
        assert os.path.exists(os.path.join(paths.OUTPUT_DIR, "vendor_onboarding_flow.png"))
        assert not os.path.exists(os.path.join(paths.OUTPUT_DIR, "Checkout_Service_flow.png"))

    def test_pinned_design_tool_ignores_a_coexisting_process_document(self):
        # The actual severe bug: the design pipeline's own diagram step,
        # unpinned, resolved via detect_schema_type_from_disk() -- which
        # ALWAYS prefers "process" whenever both files exist -- so it
        # silently rendered a stale PROCESS diagram instead of the design
        # document it had just built.
        from process_agents.common.doc_creation_agent import build_edge_inference_instance

        _write_design_json()
        _write_process_json()
        agent = build_edge_inference_instance("design")
        result = agent.tools[0]()

        assert "Diagram successfully generated at" in result
        assert os.path.exists(os.path.join(paths.OUTPUT_DIR, "Checkout_Service_flow.png"))
        assert not os.path.exists(os.path.join(paths.OUTPUT_DIR, "vendor_onboarding_flow.png"))

    def test_pinned_requirements_tool_is_a_noop_that_touches_no_disk(self):
        # Requirements summaries have no flow/architecture diagram --
        # Create_Doc_Agent's own edge-inference stage must skip them
        # rather than falling into the "process" branch (is_design is
        # only true for "design") and either erroring confusingly or
        # silently rendering a stale, unrelated process diagram.
        from process_agents.common.doc_creation_agent import build_edge_inference_instance

        _write_process_json()
        _write_design_json()
        agent = build_edge_inference_instance("requirements")
        result = agent.tools[0]()

        assert result.startswith("SKIPPED:")
        assert not os.path.exists(os.path.join(paths.OUTPUT_DIR, "vendor_onboarding_flow.png"))
        assert not os.path.exists(os.path.join(paths.OUTPUT_DIR, "Checkout_Service_flow.png"))

    def test_pinned_proposal_response_tool_is_a_noop_that_touches_no_disk(self):
        # Same reasoning as the requirements no-op above: a proposal
        # response has no flow/architecture diagram either.
        from process_agents.common.doc_creation_agent import build_edge_inference_instance

        _write_process_json()
        _write_design_json()
        agent = build_edge_inference_instance("proposal_response")
        result = agent.tools[0]()

        assert result.startswith("SKIPPED:")
        assert not os.path.exists(os.path.join(paths.OUTPUT_DIR, "vendor_onboarding_flow.png"))
        assert not os.path.exists(os.path.join(paths.OUTPUT_DIR, "Checkout_Service_flow.png"))


class TestDocGenerationPinning:
    def test_pinned_tool_has_no_llm_visible_schema_type_parameter_but_keeps_process_name(self):
        from process_agents.common.doc_creation_agent import build_doc_generation_instance

        agent = build_doc_generation_instance("design")
        assert len(agent.tools) == 1
        sig = inspect.signature(agent.tools[0])
        assert "schema_type" not in sig.parameters
        assert "process_name" in sig.parameters

    def test_pinned_design_tool_ignores_a_coexisting_process_document(self):
        from process_agents.common.doc_creation_agent import build_doc_generation_instance

        _write_design_json()
        _write_process_json()
        agent = build_doc_generation_instance("design")
        result = agent.tools[0]()

        assert result.startswith("SUCCESS:")
        out_path = os.path.join(paths.OUTPUT_DIR, "Checkout_Service.docx")
        assert os.path.exists(out_path), f"expected the DESIGN document, not the process one -- {out_path} missing"
        assert docx.Document(out_path).paragraphs

    def test_pinned_process_tool_ignores_a_coexisting_design_document(self):
        from process_agents.common.doc_creation_agent import build_doc_generation_instance

        _write_process_json()
        _write_design_json()
        agent = build_doc_generation_instance("process")
        result = agent.tools[0]()

        assert result.startswith("SUCCESS:")
        out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Onboarding.docx")
        assert os.path.exists(out_path)

    def test_pinned_requirements_tool_renders_the_requirements_document(self):
        # requirements_summary.json has no title field of its own -- name
        # comes from whatever process_name the caller/LLM passes.
        from process_agents.common.doc_creation_agent import build_doc_generation_instance

        _write_requirements_summary_json()
        _write_process_json()
        _write_design_json()
        agent = build_doc_generation_instance("requirements")
        result = agent.tools[0](process_name="Vendor Requirements")

        assert result.startswith("SUCCESS:")
        out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Requirements.docx")
        assert os.path.exists(out_path)
        assert docx.Document(out_path).paragraphs

    def test_pinned_proposal_response_tool_renders_the_proposal_response_document(self):
        # proposal_response.json has no title field of its own either --
        # name comes from whatever process_name the caller/LLM passes.
        from process_agents.common.doc_creation_agent import build_doc_generation_instance

        _write_proposal_response_json()
        _write_process_json()
        _write_design_json()
        agent = build_doc_generation_instance("proposal_response")
        result = agent.tools[0](process_name="Vendor Portal Proposal Response")

        assert result.startswith("SUCCESS:")
        out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Portal_Proposal_Response.docx")
        assert os.path.exists(out_path)
        assert docx.Document(out_path).paragraphs


class TestRealPipelineWiring:
    """Source-level lock: each real create/update pipeline must pass its
    own known, fixed schema_type to build_doc_creation_agent -- not leave
    it to auto-detection, which silently favors "process" whenever both
    process_data.json and design_data.json exist."""

    def _source(self, relative_path):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        with open(os.path.join(root, relative_path), encoding="utf-8") as f:
            return f.read()

    def test_process_create_pipeline_pins_process(self):
        text = self._source("process_agents/process/create_process_agent.py")
        assert 'build_doc_creation_agent("Create", schema_type="process")' in text

    def test_process_update_pipeline_pins_process(self):
        text = self._source("process_agents/process/update_process_agent.py")
        assert 'build_doc_creation_agent("Update", schema_type="process")' in text

    def test_design_doc_create_pipeline_pins_design(self):
        text = self._source("process_agents/design/design_doc_create_agent.py")
        assert 'build_doc_creation_agent("CreateDoc", schema_type="design")' in text

    def test_design_doc_update_pipeline_pins_design(self):
        text = self._source("process_agents/design/design_doc_update_agent.py")
        assert 'build_doc_creation_agent("UpdateDoc", schema_type="design")' in text

    def test_create_doc_agent_is_deliberately_left_unpinned(self):
        # The one genuinely domain-agnostic caller -- schema_type must stay
        # resolvable from the user's own request wording at the LLM level
        # (see instructions/common/edge_inference_agent.txt and
        # doc_generation_agent.txt), not hardcoded here.
        text = self._source("process_agents/common/agent.py")
        assert 'build_doc_creation_agent("Create_Doc_Agent")' in text
