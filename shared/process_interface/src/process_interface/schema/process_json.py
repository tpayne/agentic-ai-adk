"""Switchable per the governing principle -- see schema/togaf_json.py's
module docstring for the full reasoning. detect_schema_type_from_disk is
kept always-local: it's a convenience auto-detect fallback over THIS
process's own output directory contents, closer to the "introspect local
control state" category than "read the canonical document" -- there's no
remote equivalent, and every real pipeline already passes schema_type
explicitly rather than relying on it (see process_toolkit's own
docgen/generation.py docstring)."""

from typing import Any, Dict

from process_toolkit.schema.process_json import (
    PROCESS_JSON_FILENAME,
    detect_schema_type_from_disk,
    extract_valid_json,
    load_process_template,
    validate_process_json,
)
from process_toolkit.schema import process_json as _toolkit

from process_interface import config, paths, _transport
from process_interface.schema._common import coerce_json_content, mirror_local_copy

SCHEMA_TYPE = "process"

__all__ = [
    "SCHEMA_TYPE",
    "detect_schema_type_from_disk",
    "extract_valid_json",
    "load_process_template",
    "validate_process_json",
    "load_master_process_json",
    "load_full_process_context",
    "persist_final_json",
]


def load_master_process_json() -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call("load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()})
    return _toolkit.load_master_process_json()


def load_full_process_context() -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call("load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()})
    return _toolkit.load_full_process_context()


def persist_final_json(json_content: Any) -> str:
    if not config.is_mcp_mode():
        return _toolkit.persist_final_json(json_content)

    coerced, error_message = coerce_json_content(json_content)
    if error_message:
        return error_message
    result = _transport.call(
        "persist_json",
        {"schema_type": SCHEMA_TYPE, "data": coerced, "session_id": paths.current_session_id()},
    )
    message = result["message"]
    if message.startswith("SUCCESS"):
        mirror_local_copy(PROCESS_JSON_FILENAME, coerced)
    return message
