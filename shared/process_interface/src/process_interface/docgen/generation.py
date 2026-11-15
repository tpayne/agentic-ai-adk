"""Switchable -- create_standard_doc_from_file renders real .docx file(s)
from the session's persisted JSON baseline, so it follows PROCESS_TOOLKIT_
MODE. schema_type=None (auto-detect) is a real call pattern (the "regenerate
whichever document already exists" callers) -- resolved locally via the
always-local detect_schema_type_from_disk before the mode branch, since the
MCP server's generate_document tool requires an explicit schema_type and
there's no reason detection itself needs a network round trip (it only
ever inspects local disk, which mirror_local_copy keeps in sync regardless
of mode -- see schema/_common.py).
"""

from typing import Optional

from process_toolkit.docgen.generation import create_standard_doc_from_file as _toolkit_create
from process_toolkit.schema.process_json import detect_schema_type_from_disk

from process_interface import config, paths, _transport, _artifacts

__all__ = ["create_standard_doc_from_file"]


def create_standard_doc_from_file(
    process_name: str = "Process",
    schema_type: Optional[str] = None,
    design_variant: Optional[str] = None,
    togaf_variant: Optional[str] = None,
) -> str:
    if not config.is_mcp_mode():
        return _toolkit_create(process_name, schema_type, design_variant, togaf_variant)

    resolved_type = schema_type or detect_schema_type_from_disk()
    variant = design_variant if resolved_type == "design" else togaf_variant if resolved_type == "togaf" else None

    try:
        result = _transport.call(
            "generate_document",
            {
                "schema_type": resolved_type,
                "session_id": paths.current_session_id(),
                "variant": variant,
                "process_name": process_name,
            },
        )
    except Exception as e:
        return f"ERROR: {e}"

    message = result["message"]
    if message.startswith("SUCCESS"):
        _artifacts.materialize(result.get("documents", []))
    return message
