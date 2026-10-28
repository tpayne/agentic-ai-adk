"""Wiring coverage for the standalone cloud-architecture-restore network
(registries/cloudarch_import.hocon), added to fix a routing bug: an
uploaded cloudarch_drawio.xml with a request like "use this architectural
diagram for further questions" was being routed to Design_Import_Agent
(which re-derived a whole new design document from it via LLM extraction)
instead of being restored verbatim as the active diagram, since the router
had no cloud-architecture option in its "import an already-existing
document" decision at all.

`ns validate` (test_hocon_validation.py) checks HOCON structure but does
NOT catch a "class" reference that's syntactically fine yet resolves to
the wrong place on disk -- confirmed the hard way: this network originally
shipped with load_directory_context_tool/load_drawio_tool referenced by
their bare module names with NO coded_tools/cloudarch_import/ shim
directory at all, passed `ns validate` clean, and then failed on the live
server the first time CloudArch_Import_Agent actually tried to call
load_directory_context ("Could not find class ... under AGENT_TOOL_PATH
'coded_tools' ... in the agent network 'cloudarch_import'").
test_coded_tool_class_resolution.py now guards every network's every
"class" reference against this exact failure mode generically; the
identity checks below lock in specifically that THIS network's own shims
(coded_tools/cloudarch_import/load_directory_context_tool.py,
.../load_drawio_tool.py) re-export the real canonical classes rather than
forked copies. restore_drawio_xml_tool.py has no shim to check here --
CloudArch_Import_Agent is its only caller, so it lives directly under
coded_tools/cloudarch_import/ as its own canonical home.
"""

from pathlib import Path

from coded_tools.requirements_summary.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as CanonicalLoadDirectoryContext,
)
from coded_tools.cloudarch.load_drawio_tool import LoadDrawioCodedTool as CanonicalLoadDrawio
from coded_tools.cloudarch_import.load_directory_context_tool import LoadDirectoryContextCodedTool
from coded_tools.cloudarch_import.load_drawio_tool import LoadDrawioCodedTool
from coded_tools.cloudarch_import.restore_drawio_xml_tool import RestoreDrawioXmlCodedTool

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_cloudarch_import_shims_reexport_the_canonical_classes():
    # Imported from the network's OWN shim path above -- the same import
    # neuro-san's own resolver performs at runtime -- and asserted `is`
    # (identity, not just equality) the canonical class.
    assert LoadDirectoryContextCodedTool is CanonicalLoadDirectoryContext
    assert LoadDrawioCodedTool is CanonicalLoadDrawio


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
