"""Persists/loads a structured proposal response -- drafted against an
ALREADY-saved requirements_summary.json (an RFP/proposal's own analyzed
requirements register) -- to a single shared slot on disk
(output/proposal_response.json), so it can be re-rendered or reused
without re-drafting.

Same `state` convention as requirements_summary.py's own module: a
dict-like, per-session cache (ADK's `tool_context.state`; neuro-san's
`sly_data`), checked before the shared file so two concurrent sessions
never see each other's draft, while the shared file remains the
deliberate, single cross-process slot for explicitly reusing an earlier
run's response. Each caller's own thin wrapper passes its own state
object through; this module has no opinion on which framework it came
from, just that it supports `.get()` and item assignment like a plain
dict.
"""

import json
import os
from typing import Any, Dict, MutableMapping, Optional

from process_toolkit import paths

PROPOSAL_RESPONSE_FILENAME = "proposal_response.json"
STATE_KEY = "proposal_response"

# Any dict-like per-session cache (ADK's ToolContext.state, neuro-san's
# sly_data) -- only .get()/__setitem__ are ever used.
StateLike = MutableMapping[str, Any]


def save_proposal_response(response: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(response, dict):
        return "ERROR: response must be a JSON object."

    path = paths.output_path(PROPOSAL_RESPONSE_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(response, f, indent=2, ensure_ascii=False)
        if state is not None:
            state[STATE_KEY] = response
        return f"SUCCESS: Proposal response persisted to {path}"
    except Exception as e:
        return f"ERROR: Could not save proposal response: {e}"


def load_proposal_response(state: Optional[StateLike] = None) -> Dict[str, Any]:
    if state is not None:
        session_response = state.get(STATE_KEY)
        if isinstance(session_response, dict):
            result = dict(session_response)
            result.setdefault("status", "OK")
            return result

    path = paths.output_path(PROPOSAL_RESPONSE_FILENAME)
    if not os.path.exists(path):
        return {"status": "NOT_FOUND"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            response = json.load(f)
        if isinstance(response, dict):
            response.setdefault("status", "OK")
        return response
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
