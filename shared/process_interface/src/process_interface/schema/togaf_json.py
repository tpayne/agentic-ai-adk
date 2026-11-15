"""Switchable per the governing principle: load_master/load_full_context
and persist_final do disk I/O against the session's togaf_data.json, so
they follow PROCESS_TOOLKIT_MODE. load_togaf_template and validate_togaf_json
are pure computation over data already in hand (a static constant and a
caller-supplied dict respectively) -- always-local regardless of mode,
since there's no reason to pay a network round trip for them and no
compliance benefit either (process_interface depends on process_toolkit
either way; MCP mode changes WHERE state lives, not where computation runs).
extract_valid_json is the same kind of pure function.
"""

from typing import Any, Dict, Optional

from process_toolkit.schema.togaf_json import (
    TOGAF_JSON_FILENAME,
    extract_valid_json,
    load_togaf_template,
    validate_togaf_json,
)
from process_toolkit.schema import togaf_json as _toolkit

from process_interface import config, paths, _transport
from process_interface.schema._common import coerce_json_content, mirror_local_copy

SCHEMA_TYPE = "togaf"

__all__ = [
    "TOGAF_JSON_FILENAME",
    "SCHEMA_TYPE",
    "extract_valid_json",
    "load_togaf_template",
    "validate_togaf_json",
    "load_master_togaf_json",
    "load_full_togaf_context",
    "persist_final_togaf_json",
]


def load_master_togaf_json() -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call("load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()})
    return _toolkit.load_master_togaf_json()


def load_full_togaf_context() -> Dict[str, Any]:
    """Same content as load_master_togaf_json -- kept as a separate name
    for the scenario-tester agent, mirroring process_toolkit's own."""
    if config.is_mcp_mode():
        return _transport.call("load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()})
    return _toolkit.load_full_togaf_context()


def persist_final_togaf_json(json_content: Any) -> str:
    if not config.is_mcp_mode():
        return _toolkit.persist_final_togaf_json(json_content)

    coerced, error_message = coerce_json_content(json_content)
    if error_message:
        return error_message
    result = _transport.call(
        "persist_json",
        {"schema_type": SCHEMA_TYPE, "data": coerced, "session_id": paths.current_session_id()},
    )
    message = result["message"]
    if message.startswith("SUCCESS"):
        mirror_local_copy(TOGAF_JSON_FILENAME, coerced)
    return message
