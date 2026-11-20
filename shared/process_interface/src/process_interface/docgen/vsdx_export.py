"""Switchable -- build_process_design_vsdx/build_cloudarch_vsdx render real
.vsdx files from the session's persisted JSON/drawio-XML baseline, so they
follow PROCESS_TOOLKIT_MODE exactly like docgen/edge_inference.py's own
generate_clean_diagram and docgen/generation.py's own
create_standard_doc_from_file.

Materialization is gated on the returned "vsdx" payload itself being
present (server.py's own export tools set it exactly when a new .vsdx was
produced), NOT on matching a hand-copied message prefix -- see
docgen/edge_inference.py's own "CONFIRMED AS A REAL BUG" comment for why a
prefix check silently breaks the moment the underlying toolkit function's
own wording doesn't happen to start with that exact string.
"""

from process_toolkit.docgen.vsdx_export import (
    CLOUDARCH_VSDX_FILENAME,
    DESIGN_FLOW_VSDX_FILENAME,
    PROCESS_FLOW_VSDX_FILENAME,
    build_cloudarch_vsdx as _toolkit_build_cloudarch_vsdx,
    build_process_design_vsdx as _toolkit_build_process_design_vsdx,
    cloudarch_vsdx_exists,
    design_flow_vsdx_exists,
    parse_vsdx_to_graph,
    process_flow_vsdx_exists,
)

from process_interface import _artifacts, _transport, config, paths

__all__ = [
    "build_process_design_vsdx", "build_cloudarch_vsdx",
    "PROCESS_FLOW_VSDX_FILENAME", "DESIGN_FLOW_VSDX_FILENAME", "CLOUDARCH_VSDX_FILENAME",
    "process_flow_vsdx_exists", "design_flow_vsdx_exists", "cloudarch_vsdx_exists",
    "parse_vsdx_to_graph",
]

# The *_exists() checks, filename constants, and parse_vsdx_to_graph all
# stay always-local (same reasoning as iac/generation.py's own
# iac_zip_exists) -- they read the LOCAL output dir, which
# materialize_one() already mirrors a successful MCP-mode export into, so
# there's nothing for these to redirect to the server for.


def build_process_design_vsdx(schema_type: str) -> str:
    if not config.is_mcp_mode():
        return _toolkit_build_process_design_vsdx(schema_type)

    try:
        result = _transport.call(
            "export_process_design_vsdx",
            {"schema_type": schema_type, "session_id": paths.current_session_id()},
        )
    except Exception as e:
        return f"ERROR: {e}"

    message = result["message"]
    if result.get("vsdx"):
        _artifacts.materialize_one(result.get("vsdx"))
    return message


def build_cloudarch_vsdx() -> str:
    if not config.is_mcp_mode():
        return _toolkit_build_cloudarch_vsdx()

    try:
        result = _transport.call("export_cloudarch_vsdx", {"session_id": paths.current_session_id()})
    except Exception as e:
        return f"ERROR: {e}"

    message = result["message"]
    if result.get("vsdx"):
        _artifacts.materialize_one(result.get("vsdx"))
    return message
