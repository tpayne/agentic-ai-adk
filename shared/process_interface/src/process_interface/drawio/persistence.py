"""Switchable -- reads/writes the session's own cloud-architecture diagram
XML, so follows PROCESS_TOOLKIT_MODE. parse_drawio_graph (drawio/graph.py,
a sibling module) stays always-local since it's pure XML-string-in/graph-
out with no I/O of its own.
"""

from process_toolkit.drawio.persistence import DRAWIO_FILENAME
from process_toolkit.drawio import persistence as _toolkit

from process_interface import config, paths, _transport

__all__ = ["DRAWIO_FILENAME", "load_drawio_xml", "reset_drawio_xml"]


def load_drawio_xml() -> dict:
    if config.is_mcp_mode():
        return _transport.call("load_drawio", {"session_id": paths.current_session_id()})
    return _toolkit.load_drawio_xml()


def reset_drawio_xml() -> None:
    if config.is_mcp_mode():
        _transport.call("reset_drawio", {"session_id": paths.current_session_id()})
        return
    _toolkit.reset_drawio_xml()
