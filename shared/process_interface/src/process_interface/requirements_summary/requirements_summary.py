"""Switchable, but the `state` check happens locally regardless of mode --
`state` is ADK's ToolContext.state / neuro-san's sly_data, a per-session
object alive only in the CALLING agent process; it can't be sent over the
network and shouldn't be, so this module replicates process_toolkit's own
"check state first, fall back to the baseline" shape itself rather than
delegating the whole function to one mode or the other. Only the baseline
fallback (disk locally / persist_json+load_context over MCP) actually
switches.
"""

from typing import Any, Dict, Optional

from process_toolkit.requirements_summary.requirements_summary import (
    REQUIREMENTS_SUMMARY_FILENAME,
    STATE_KEY,
    StateLike,
)
from process_toolkit.requirements_summary import requirements_summary as _toolkit

from process_interface import config, paths, _transport

SCHEMA_TYPE = "requirements"

__all__ = [
    "REQUIREMENTS_SUMMARY_FILENAME",
    "STATE_KEY",
    "StateLike",
    "save_requirements_summary",
    "load_requirements_summary",
    "update_requirements_summary",
]


def save_requirements_summary(summary: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(summary, dict):
        return "ERROR: summary must be a JSON object."

    if not config.is_mcp_mode():
        return _toolkit.save_requirements_summary(summary, state)

    try:
        result = _transport.call(
            "persist_json",
            {"schema_type": SCHEMA_TYPE, "data": summary, "session_id": paths.current_session_id()},
        )
        message = result["message"]
    except Exception as e:
        return f"ERROR: Could not save requirements summary: {e}"

    if message.startswith("SUCCESS") and state is not None:
        state[STATE_KEY] = summary
    return message


def load_requirements_summary(state: Optional[StateLike] = None) -> Dict[str, Any]:
    if state is not None:
        session_summary = state.get(STATE_KEY)
        if isinstance(session_summary, dict):
            result = dict(session_summary)
            result.setdefault("status", "OK")
            return result

    if not config.is_mcp_mode():
        return _toolkit.load_requirements_summary(None)  # state already checked above

    try:
        return _transport.call(
            "load_context", {"schema_type": SCHEMA_TYPE, "session_id": paths.current_session_id()}
        )
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def update_requirements_summary(patch: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(patch, dict):
        return "ERROR: patch must be a JSON object."

    existing = load_requirements_summary(state)
    if not isinstance(existing, dict) or existing.get("status") in ("NOT_FOUND", "ERROR"):
        return "ERROR: No existing requirements summary to update -- save one first."

    existing.pop("status", None)
    existing.update(patch)
    return save_requirements_summary(existing, state)
