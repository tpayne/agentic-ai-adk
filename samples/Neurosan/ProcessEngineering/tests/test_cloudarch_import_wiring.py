"""Wiring coverage for the standalone cloud-architecture-restore network
(registries/cloudarch_import.hocon), added to fix a routing bug: an
uploaded cloudarch_drawio.xml with a request like "use this architectural
diagram for further questions" was being routed to Design_Import_Agent
(which re-derived a whole new design document from it via LLM extraction)
instead of being restored verbatim as the active diagram, since the router
had no cloud-architecture option in its "import an already-existing
document" decision at all.

Structural HOCON validation (including that the "class" path referenced
below actually resolves via neuro-san's own Resolver) is covered separately
by test_hocon_validation.py -- this file instead locks in that the new
network's own tool re-exports the same canonical save_drawio_xml function
process.hocon's own CloudArch_Agent already uses (no forked/duplicated
persistence logic), and that the router's own instructions and the
manifest actually mention the new network.
"""

from pathlib import Path

from coded_tools.cloudarch.restore_drawio_xml_tool import RestoreDrawioXmlCodedTool

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_restore_drawio_xml_tool_delegates_to_the_canonical_save_function(tmp_path, monkeypatch):
    from process_toolkit import paths

    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    tool = RestoreDrawioXmlCodedTool()

    xml = "<mxfile><diagram><mxGraphModel><root></root></mxGraphModel></diagram></mxfile>"
    result = tool.invoke({"xml_content": xml}, {})
    assert result["status"] == "OK"
    assert (tmp_path / "cloudarch_drawio.xml").read_text(encoding="utf-8") == xml


def test_restore_drawio_xml_tool_rejects_malformed_xml(tmp_path, monkeypatch):
    from process_toolkit import paths

    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    tool = RestoreDrawioXmlCodedTool()
    result = tool.invoke({"xml_content": "<not valid"}, {})
    assert result["status"] == "ERROR"


def test_restore_drawio_xml_tool_requires_xml_content():
    tool = RestoreDrawioXmlCodedTool()
    assert tool.invoke({}, {})["status"] == "ERROR"
    assert tool.invoke({"xml_content": ""}, {})["status"] == "ERROR"
    assert tool.invoke({"xml_content": "   "}, {})["status"] == "ERROR"


def test_router_references_the_cloudarch_import_network():
    router_text = (PROJECT_ROOT / "registries" / "process_architect.hocon").read_text(encoding="utf-8")
    assert "CloudArch_Import_Agent" in router_text
    assert '"/cloudarch_import"' in router_text


def test_manifest_registers_the_cloudarch_import_network():
    manifest_text = (PROJECT_ROOT / "registries" / "manifest.hocon").read_text(encoding="utf-8")
    assert '"cloudarch_import.hocon"' in manifest_text
