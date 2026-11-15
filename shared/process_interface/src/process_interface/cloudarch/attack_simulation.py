"""Switchable -- see cloudarch/simulation.py's module docstring for the
full reasoning; mirrors it exactly for the attack-path simulation."""

from typing import Any

from process_toolkit.cloudarch.attack_simulation import simulate_cloudarch_attack as _toolkit_simulate

from process_interface import config, paths, _transport

__all__ = ["simulate_cloudarch_attack"]


def simulate_cloudarch_attack(xml_content: Any = None) -> str:
    if config.is_mcp_mode():
        return _transport.call(
            "simulate_attack", {"xml_content": xml_content, "session_id": paths.current_session_id()}
        )
    return _toolkit_simulate(xml_content)
