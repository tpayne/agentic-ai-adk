"""Switchable -- falls back to the session's saved itsm_data.json, so
follows PROCESS_TOOLKIT_MODE. Returns a plain dict (not a JSON-encoded
string -- unlike cloudarch/simulation.py's own wrapper, which matches
process_toolkit's pre-existing cloudarch return type; this function's own
process_toolkit return type is already a plain dict, so there's nothing
to match here)."""

from typing import Any, Dict, Optional

from process_toolkit.itsm.simulation import simulate_itsm_risk_and_coverage as _toolkit_simulate

from process_interface import config, paths, _transport

__all__ = ["simulate_itsm_risk_and_coverage"]


def simulate_itsm_risk_and_coverage(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call("simulate_itsm_risk", {"session_id": paths.current_session_id()})
    return _toolkit_simulate(data)
