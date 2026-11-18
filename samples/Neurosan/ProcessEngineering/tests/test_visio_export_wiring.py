"""Wiring coverage for the two standalone Visio-export networks
(registries/process_visio_export.hocon, registries/cloudarch_visio_export.hocon),
mirroring test_subprocess_regenerate_wiring.py's own coverage shape --
`ns validate` (test_hocon_validation.py) checks HOCON structure but not
whether the router actually mentions these networks, or whether their own
CodedTool classes genuinely call through to process_interface rather than
some other, forked implementation (test_coded_tool_class_resolution.py
already guards every network's "class" references generically against a
missing/misnamed module; this file locks in the router/manifest wiring
plus a real behavioral round trip through each CodedTool).
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_router_references_both_visio_export_networks():
    router_text = (PROJECT_ROOT / "registries" / "process_architect.hocon").read_text(encoding="utf-8")
    assert "VISIO (.vsdx) EXPORT" in router_text
    assert "`/process_visio_export`" in router_text
    assert '"/process_visio_export"' in router_text
    assert "`/cloudarch_visio_export`" in router_text
    assert '"/cloudarch_visio_export"' in router_text


def test_manifest_registers_both_visio_export_networks():
    manifest_text = (PROJECT_ROOT / "registries" / "manifest.hocon").read_text(encoding="utf-8")
    assert '"process_visio_export.hocon"' in manifest_text
    assert '"cloudarch_visio_export.hocon"' in manifest_text


def test_export_process_design_vsdx_tool_rejects_an_unknown_schema_type():
    from coded_tools.process_visio_export.vsdx_export_tool import ExportProcessDesignVsdxCodedTool

    tool = ExportProcessDesignVsdxCodedTool()
    assert tool.invoke({"schema_type": "requirements"}, {}).startswith("ERROR:")


def test_export_process_design_vsdx_tool_exports_the_start_end_fallback():
    # No process_data.json saved -- _infer_edges_from_json's own Start->End
    # fallback still produces a real file, same contract
    # test_build_process_design_vsdx_falls_back_to_a_start_end_placeholder_
    # when_no_process_data pins down at the process_toolkit layer; this
    # test proves the CodedTool wiring reaches that same real function.
    from coded_tools.process_visio_export.vsdx_export_tool import ExportProcessDesignVsdxCodedTool

    tool = ExportProcessDesignVsdxCodedTool()
    result = tool.invoke({"schema_type": "process"}, {})
    assert result.startswith("Visio diagram successfully exported to "), result


def test_export_cloudarch_vsdx_tool_errors_cleanly_with_nothing_saved():
    from coded_tools.cloudarch_visio_export.vsdx_export_tool import ExportCloudarchVsdxCodedTool

    tool = ExportCloudarchVsdxCodedTool()
    assert tool.invoke({}, {}).startswith("ERROR:")
