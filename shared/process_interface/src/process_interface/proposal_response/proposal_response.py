"""Switchable -- see requirements_summary/requirements_summary.py's module
docstring for the full reasoning; mirrors it exactly for proposal_response."""

from typing import Any, Dict, Optional

from process_toolkit.proposal_response.proposal_response import (
    PROPOSAL_RESPONSE_FILENAME,
    STATE_KEY,
    StateLike,
)
from process_toolkit.proposal_response import proposal_response as _toolkit

from process_interface import config, paths, _transport

SCHEMA_TYPE = "proposal_response"

__all__ = [
    "PROPOSAL_RESPONSE_FILENAME",
    "STATE_KEY",
    "StateLike",
    "save_proposal_response",
    "load_proposal_response",
    "update_proposal_response",
]


def save_proposal_response(response: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(response, dict):
        return "ERROR: response must be a JSON object."

    if not config.is_mcp_mode():
        return _toolkit.save_proposal_response(response, state)

    try:
        result = _transport.call(
            "persist_json",
            {"schema_type": SCHEMA_TYPE, "data": response, "session_id": paths.current_session_id()},
        )
        message = result["message"]
    except Exception as e:
        return f"ERROR: Could not save proposal response: {e}"

    if message.startswith("SUCCESS") and state is not None:
        state[STATE_KEY] = response
    return message


def load_proposal_response(state: Optional[StateLike] = None) -> Dict[str, Any]:
    if state is not None:
        session_response = state.get(STATE_KEY)
        if isinstance(session_response, dict):
            result = dict(session_response)
            result.setdefault("status", "OK")
            return result

    if not config.is_mcp_mode():
        return _toolkit.load_proposal_response(None)

    try:
        return _transport.call(
            "load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()}
        )
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def update_proposal_response(patch: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(patch, dict):
        return "ERROR: patch must be a JSON object."

    existing = load_proposal_response(state)
    if not isinstance(existing, dict) or existing.get("status") in ("NOT_FOUND", "ERROR"):
        return "ERROR: No existing proposal response to update -- save one first."

    existing.pop("status", None)
    existing.update(patch)
    return save_proposal_response(existing, state)
