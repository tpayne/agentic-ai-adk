"""Persists/loads a structured requirements summary -- built from
load_directory_context's extracted text -- to a single shared slot on
disk (output/requirements_summary.json), so a LATER process/design/
cloudarch creation request can reuse it instead of re-reading the
original directory.

`state` is a dict-like, per-session cache (ADK's `tool_context.state`;
neuro-san's `sly_data`) -- checked before the shared file so that two
concurrent sessions each calling save then load never see each other's
summary, while the shared file remains the deliberate, single
cross-process slot for explicitly reusing an earlier run's summary.
Each caller's own thin wrapper passes its own state object through; this
module has no opinion on which framework it came from, just that it
supports `.get()` and item assignment like a plain dict.
"""

import json
import os
from typing import Any, Dict, MutableMapping, Optional

from process_toolkit import paths

REQUIREMENTS_SUMMARY_FILENAME = "requirements_summary.json"
STATE_KEY = "requirements_summary"

# Any dict-like per-session cache (ADK's ToolContext.state, neuro-san's
# sly_data) -- only .get()/__setitem__ are ever used.
StateLike = MutableMapping[str, Any]


def save_requirements_summary(summary: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(summary, dict):
        return "ERROR: summary must be a JSON object."

    path = paths.output_path(REQUIREMENTS_SUMMARY_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        if state is not None:
            state[STATE_KEY] = summary
        return f"SUCCESS: Requirements summary persisted to {path}"
    except Exception as e:
        return f"ERROR: Could not save requirements summary: {e}"


def load_requirements_summary(state: Optional[StateLike] = None) -> Dict[str, Any]:
    if state is not None:
        session_summary = state.get(STATE_KEY)
        if isinstance(session_summary, dict):
            result = dict(session_summary)
            result.setdefault("status", "OK")
            return result

    path = paths.output_path(REQUIREMENTS_SUMMARY_FILENAME)
    if not os.path.exists(path):
        return {"status": "NOT_FOUND"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        if isinstance(summary, dict):
            summary.setdefault("status", "OK")
        return summary
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
