"""Switchable per the governing principle -- see schema/togaf_json.py's
module docstring for the full reasoning; this mirrors it exactly for the
design domain."""

from typing import Any, Dict

from process_toolkit.schema.design_json import (
    DESIGN_JSON_FILENAME,
    extract_valid_json,
    load_design_template,
    validate_design_json,
)
from process_toolkit.schema import design_json as _toolkit

from process_interface import config, paths, _transport
from process_interface.schema._common import coerce_json_content, mirror_local_copy

SCHEMA_TYPE = "design"

__all__ = [
    "SCHEMA_TYPE",
    "extract_valid_json",
    "load_design_template",
    "validate_design_json",
    "load_master_design_json",
    "load_full_design_context",
    "persist_final_design_json",
]


def load_master_design_json() -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call("load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()})
    return _toolkit.load_master_design_json()


def load_full_design_context() -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call("load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()})
    return _toolkit.load_full_design_context()


def persist_final_design_json(json_content: Any) -> str:
    if not config.is_mcp_mode():
        return _toolkit.persist_final_design_json(json_content)

    coerced, error_message = coerce_json_content(json_content)
    if error_message:
        return error_message
    result = _transport.call(
        "persist_json",
        {"schema_type": SCHEMA_TYPE, "data": coerced, "session_id": paths.current_session_id()},
    )
    message = result["message"]
    if message.startswith("SUCCESS"):
        mirror_local_copy(DESIGN_JSON_FILENAME, coerced)
    return message
