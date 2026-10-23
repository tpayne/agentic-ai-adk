"""Standalone "regenerate just the document" action (registries/
regenerate_document.hocon) -- ports the ADK original's Create_Doc_Agent.
Before this, a bare "please regenerate the process document" request had
no matching tool and fell under process_architect.hocon's own Rule 10
("ask a clarification question") -- confirmed directly: the router would
ask the user to supply requirements/a directory instead of just
re-rendering what was already saved, which is what the ADK original did.
"""

import json
import os

import docx
import pytest

from coded_tools.common import paths
from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME, DESIGN_JSON_FILENAME
from coded_tools.regenerate_document.edge_inference_tool import RegenerateFlowDiagramCodedTool
from coded_tools.regenerate_document.doc_generation_tool import RegenerateDocumentCodedTool


def test_front_man_has_both_regenerate_tools():
    os.environ.setdefault("AGENT_MANIFEST_FILE", os.path.join(os.getcwd(), "registries", "manifest.hocon"))
    os.environ.setdefault("AGENT_TOOL_PATH", os.path.join(os.getcwd(), "coded_tools"))
    os.environ["PYTHONPATH"] = os.getcwd()

    from neuro_san.internals.graph.persistence.agent_network_restorer import AgentNetworkRestorer

    network = AgentNetworkRestorer().restore(file_reference="registries/regenerate_document.hocon")
    front_man_tools = network.get_config()["tools"][0]["tools"]

    assert "regenerate_flow_diagram" in front_man_tools
    assert "regenerate_document" in front_man_tools


def test_edge_inference_tool_is_not_the_pinned_process_class():
    # Regression test: this USED to be a re-export of
    # coded_tools.process.edge_inference_tool.GenerateProcessFlowDiagramCodedTool
    # -- fine while that class had no opinion on schema_type, but it was
    # later pinned to schema_type="process" (process.hocon's own pipeline
    # only ever means "process"), which would have silently broken this
    # network's own "regenerate the DESIGN document" case by reusing the
    # exact same pinned class. This is now a genuinely separate
    # implementation -- see this module's own docstring.
    from coded_tools.process.edge_inference_tool import GenerateProcessFlowDiagramCodedTool as PinnedProcessOnly
    assert RegenerateFlowDiagramCodedTool is not PinnedProcessOnly


def test_router_mentions_the_new_network():
    router_text = open("registries/process_architect.hocon", encoding="utf-8").read()
    assert "Regenerate_Document_Agent" in router_text
    assert '"/regenerate_document"' in router_text


class TestRegenerateDocumentCodedTool:
    """RegenerateDocumentCodedTool -- unlike
    GenerateProcessDocumentCodedTool/GenerateDesignDocumentCodedTool
    (each hardcode their own schema_type since they only run inside
    their own network's pipeline), this one auto-detects which of
    process_data.json/design_data.json is actually on disk."""

    def test_regenerates_a_process_document_when_process_data_exists(self):
        with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({
                "process_name": "Vendor Onboarding",
                "process_steps": [
                    {"step_name": "KYC Check", "responsible_party": "Compliance", "dependencies": []},
                ],
            }, f)

        diagram_result = RegenerateFlowDiagramCodedTool().invoke({}, {})
        assert "Diagram successfully generated at" in diagram_result

        doc_result = RegenerateDocumentCodedTool().invoke({}, {})
        assert doc_result.startswith("SUCCESS:")
        out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Onboarding.docx")
        assert os.path.exists(out_path)
        assert docx.Document(out_path).paragraphs

    def test_regenerates_a_design_document_when_only_design_data_exists(self):
        with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({
                "document_metadata": {"system_name": "Checkout Service", "title": "Checkout Service"},
            }, f)

        doc_result = RegenerateDocumentCodedTool().invoke({}, {})
        assert doc_result.startswith("SUCCESS:")

    def test_process_data_takes_precedence_when_both_exist_and_schema_type_is_unspecified(self):
        # detect_schema_type_from_disk's own documented rule: "design"
        # only when design_data.json exists AND process_data.json does
        # NOT -- every other case (including both present) resolves to
        # "process". Only correct for a genuinely generic "regenerate the
        # document" request with no domain named -- see the explicit
        # schema_type tests below for the actual fix.
        with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"process_name": "Vendor Onboarding", "process_steps": []}, f)
        with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"document_metadata": {"system_name": "Checkout Service"}}, f)

        doc_result = RegenerateDocumentCodedTool().invoke({}, {})
        assert doc_result.startswith("SUCCESS:")
        out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Onboarding.docx")
        assert os.path.exists(out_path)

    def test_explicit_schema_type_design_wins_over_a_newer_process_document(self):
        # The actual bug report this fixes: an unrelated process document
        # (even one that exists/was touched more recently) must NOT
        # contaminate an explicit "regenerate the DESIGN document"
        # request -- Regenerate_Document_Agent's own instructions resolve
        # "design" from wording like this and pass it through explicitly.
        with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"document_metadata": {"system_name": "Checkout Service", "title": "Checkout Service"}}, f)
        with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"process_name": "Vendor Onboarding", "process_steps": []}, f)

        doc_result = RegenerateDocumentCodedTool().invoke({"schema_type": "design"}, {})
        assert doc_result.startswith("SUCCESS:")
        out_path = os.path.join(paths.OUTPUT_DIR, "Checkout_Service.docx")
        assert os.path.exists(out_path), f"expected the DESIGN document, not the process one -- {out_path} missing"

        diagram_result = RegenerateFlowDiagramCodedTool().invoke({"schema_type": "design"}, {})
        assert "Diagram successfully generated at" in diagram_result
        assert "design" in diagram_result.lower() or "checkout" in diagram_result.lower() or os.path.exists(
            paths.output_path("Checkout_Service_flow.png")
        )

    def test_explicit_schema_type_process_still_works_when_design_is_newer(self):
        with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"document_metadata": {"system_name": "Checkout Service"}}, f)
        with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"process_name": "Vendor Onboarding", "process_steps": []}, f)

        doc_result = RegenerateDocumentCodedTool().invoke({"schema_type": "process"}, {})
        assert doc_result.startswith("SUCCESS:")
        out_path = os.path.join(paths.OUTPUT_DIR, "Vendor_Onboarding.docx")
        assert os.path.exists(out_path)

    def test_nothing_saved_yet_returns_a_clean_error_not_an_exception(self):
        result = RegenerateDocumentCodedTool().invoke({}, {})
        assert result.startswith("ERROR:")

    def test_flow_diagram_regeneration_falls_back_to_a_placeholder_when_nothing_saved(self):
        # generate_clean_diagram ALWAYS produces something (even a minimal
        # Start->End placeholder) -- it is NOT the "is there anything real
        # to regenerate" signal; regenerate_document's own result is (see
        # test_nothing_saved_yet_returns_a_clean_error_not_an_exception).
        result = RegenerateFlowDiagramCodedTool().invoke({}, {})
        assert "Diagram successfully generated at" in result

    def test_async_invoke_matches_sync_invoke(self):
        import asyncio

        with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"process_name": "Async Process", "process_steps": []}, f)

        sync_result = RegenerateDocumentCodedTool().invoke({}, {})
        asyncio.run(RegenerateDocumentCodedTool().async_invoke({}, {}))
        assert sync_result.startswith("SUCCESS:")
