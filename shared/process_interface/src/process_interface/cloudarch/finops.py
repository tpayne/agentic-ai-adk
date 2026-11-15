"""Switchable -- see cloudarch/simulation.py's module docstring for the
full reasoning; mirrors it exactly for the cost/finops estimate."""

from typing import Any

from process_toolkit.cloudarch.finops import estimate_cloudarch_finops as _toolkit_estimate

from process_interface import config, paths, _transport

__all__ = ["estimate_cloudarch_finops"]


def estimate_cloudarch_finops(xml_content: Any = None) -> str:
    if config.is_mcp_mode():
        return _transport.call(
            "estimate_finops", {"xml_content": xml_content, "session_id": paths.current_session_id()}
        )
    return _toolkit_estimate(xml_content)
