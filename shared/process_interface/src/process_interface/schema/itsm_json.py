"""Switchable per the governing principle: load_master/load_full_context
and persist_final do disk I/O against the session's itsm_data.json, so
they follow PROCESS_TOOLKIT_MODE. load_itsm_template and validate_itsm_json
are pure computation over data already in hand (a static constant and a
caller-supplied dict respectively) -- always-local regardless of mode,
same reasoning as togaf_json.py's own identical wrapper.
"""

from typing import Any, Dict, Optional

from process_toolkit.schema.itsm_json import (
    ITSM_JSON_FILENAME,
    extract_valid_json,
    load_itsm_template,
    validate_itsm_json,
)
from process_toolkit.schema import itsm_json as _toolkit

from process_interface import config, paths, _transport
from process_interface.schema._common import coerce_json_content, mirror_local_copy

SCHEMA_TYPE = "itsm"

__all__ = [
    "ITSM_JSON_FILENAME",
    "SCHEMA_TYPE",
    "extract_valid_json",
    "load_itsm_template",
    "validate_itsm_json",
    "load_master_itsm_json",
    "load_full_itsm_context",
    "persist_final_itsm_json",
]


def load_master_itsm_json() -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call("load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()})
    return _toolkit.load_master_itsm_json()


def load_full_itsm_context() -> Dict[str, Any]:
    """Same content as load_master_itsm_json -- kept as a separate name
    for the scenario-tester/reviewer/consultant agents, mirroring
    process_toolkit's own."""
    if config.is_mcp_mode():
        return _transport.call("load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()})
    return _toolkit.load_full_itsm_context()


def persist_final_itsm_json(json_content: Any) -> str:
    if not config.is_mcp_mode():
        return _toolkit.persist_final_itsm_json(json_content)

    coerced, error_message = coerce_json_content(json_content)
    if error_message:
        return error_message
    result = _transport.call(
        "persist_json",
        {"schema_type": SCHEMA_TYPE, "data": coerced, "session_id": paths.current_session_id()},
    )
    message = result["message"]
    if message.startswith("SUCCESS"):
        mirror_local_copy(ITSM_JSON_FILENAME, coerced)
    return message
