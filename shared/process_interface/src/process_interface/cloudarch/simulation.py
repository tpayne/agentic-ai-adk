"""Switchable -- falls back to the session's saved diagram and persists a
results JSON, so follows PROCESS_TOOLKIT_MODE. Returns a JSON-encoded
string (not a dict), matching process_toolkit's own return type exactly,
including its own {"error": ...}-shaped string on failure -- this
function never raises for a missing diagram or bad input, so there's no
exception-handling asymmetry to reconcile between modes."""

from typing import Any

from process_toolkit.cloudarch.simulation import simulate_cloudarch_architecture as _toolkit_simulate

from process_interface import config, paths, _transport

__all__ = ["simulate_cloudarch_architecture"]


def simulate_cloudarch_architecture(xml_content: Any = None) -> str:
    if config.is_mcp_mode():
        return _transport.call(
            "simulate_architecture", {"xml_content": xml_content, "session_id": paths.current_session_id()}
        )
    return _toolkit_simulate(xml_content)
