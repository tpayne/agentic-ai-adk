"""Persists/loads a structured test specification -- built from whichever
of a saved requirements summary, design document, and cloud architecture
diagram are present -- to a single shared slot on disk
(output/test_specification.json). Mirrors requirements_summary.py's own
save/load/update shape and reasoning exactly; see that module's own
docstring for the `state` parameter's purpose (a dict-like, per-session
cache checked before the shared file, so two concurrent sessions never
see each other's test specification).
"""

import json
import os
from typing import Any, Dict, MutableMapping, Optional

from process_toolkit import paths

TEST_SPECIFICATION_FILENAME = "test_specification.json"
STATE_KEY = "test_specification"

StateLike = MutableMapping[str, Any]


def save_test_specification(specification: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    if not isinstance(specification, dict):
        return "ERROR: specification must be a JSON object."

    path = paths.output_path(TEST_SPECIFICATION_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(specification, f, indent=2, ensure_ascii=False)
        if state is not None:
            state[STATE_KEY] = specification
        return f"SUCCESS: Test specification persisted to {path}"
    except Exception as e:
        return f"ERROR: Could not save test specification: {e}"


def load_test_specification(state: Optional[StateLike] = None) -> Dict[str, Any]:
    if state is not None:
        session_spec = state.get(STATE_KEY)
        if isinstance(session_spec, dict):
            result = dict(session_spec)
            result.setdefault("status", "OK")
            return result

    path = paths.output_path(TEST_SPECIFICATION_FILENAME)
    if not os.path.exists(path):
        return {"status": "NOT_FOUND"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            specification = json.load(f)
        if isinstance(specification, dict):
            specification.setdefault("status", "OK")
        return specification
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def update_test_specification(patch: Dict[str, Any], state: Optional[StateLike] = None) -> str:
    """Shallow-merges `patch` onto the existing saved test specification
    (patch keys overwrite, untouched keys survive) and re-persists via
    save_test_specification -- for a reviewer agent applying targeted
    corrections rather than re-synthesizing the whole document."""
    if not isinstance(patch, dict):
        return "ERROR: patch must be a JSON object."

    existing = load_test_specification(state)
    if not isinstance(existing, dict) or existing.get("status") in ("NOT_FOUND", "ERROR"):
        return "ERROR: No existing test specification to update -- save one first."

    existing.pop("status", None)
    existing.update(patch)
    return save_test_specification(existing, state)
