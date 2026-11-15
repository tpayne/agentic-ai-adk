"""Switchable -- see requirements_summary/requirements_summary.py's module
docstring for the full reasoning; mirrors it exactly for test_specification."""

from typing import Any, Dict, Optional

from process_toolkit.test_specification.test_specification import (
    STATE_KEY,
    TEST_SPECIFICATION_FILENAME,
    StateLike,
)
from process_toolkit.test_specification import test_specification as _toolkit

from process_interface import config, paths, _transport

SCHEMA_TYPE = "test_specification"

__all__ = [
    "TEST_SPECIFICATION_FILENAME",
    "STATE_KEY",
    "StateLike",
    "save_test_specification",
    "load_test_specification",
    "update_test_specification",
]


def save_test_specification(specification: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(specification, dict):
        return "ERROR: specification must be a JSON object."

    if not config.is_mcp_mode():
        return _toolkit.save_test_specification(specification, state)

    try:
        result = _transport.call(
            "persist_json",
            {"schema_type": SCHEMA_TYPE, "data": specification, "session_id": paths.current_session_id()},
        )
        message = result["message"]
    except Exception as e:
        return f"ERROR: Could not save test specification: {e}"

    if message.startswith("SUCCESS") and state is not None:
        state[STATE_KEY] = specification
    return message


def load_test_specification(state: Optional[StateLike] = None) -> Dict[str, Any]:
    if state is not None:
        session_spec = state.get(STATE_KEY)
        if isinstance(session_spec, dict):
            result = dict(session_spec)
            result.setdefault("status", "OK")
            return result

    if not config.is_mcp_mode():
        return _toolkit.load_test_specification(None)

    try:
        return _transport.call(
            "load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()}
        )
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def update_test_specification(patch: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(patch, dict):
        return "ERROR: patch must be a JSON object."

    existing = load_test_specification(state)
    if not isinstance(existing, dict) or existing.get("status") in ("NOT_FOUND", "ERROR"):
        return "ERROR: No existing test specification to update -- save one first."

    existing.pop("status", None)
    existing.update(patch)
    return save_test_specification(existing, state)
