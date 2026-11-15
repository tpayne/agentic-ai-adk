"""load_process_steps is derived from the already-switchable
load_master_process_json (process_json.py) -- pure computation (filtering)
over data that module already fetched correctly for the active mode, so
no new network call is needed here. validate_subprocess_flow is pure,
always-local. save_subprocess_flow is genuinely switchable -- writes a
new file under the session's own subprocesses/ subdirectory.
"""

from typing import Any, Dict, List

from process_toolkit.schema.subprocess_json import validate_subprocess_flow
from process_toolkit.schema.subprocess_json import save_subprocess_flow as _toolkit_save

from process_interface import config, paths, _transport
from process_interface.schema.process_json import load_master_process_json

__all__ = ["load_process_steps", "validate_subprocess_flow", "save_subprocess_flow"]


def load_process_steps() -> List[Dict[str, Any]]:
    data = load_master_process_json()
    steps = data.get("process_steps", [])
    if not isinstance(steps, list):
        return []
    return [s for s in steps if isinstance(s, dict) and s.get("step_name")]


def save_subprocess_flow(step_name: str, flow: Dict[str, Any]) -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call(
            "save_subprocess_flow",
            {"step_name": step_name, "flow": flow, "session_id": paths.current_session_id()},
        )
    return _toolkit_save(step_name, flow)
