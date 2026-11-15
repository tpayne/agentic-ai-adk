"""Switchable -- generic reader for whichever of design_data.json/
process_data.json exists in the session's own output directory, so
follows PROCESS_TOOLKIT_MODE. Equivalent to load_context("design"/
"process") when schema_type is given explicitly; this module exists
specifically for the schema_type=None auto-detect-by-mtime case neither
of those two cover.
"""

from typing import Optional

from process_toolkit.schema.master_json import load_master_json as _toolkit_load

from process_interface import config, paths, _transport

__all__ = ["load_master_json"]


def load_master_json(schema_type: Optional[str] = None) -> dict:
    if config.is_mcp_mode():
        return _transport.call(
            "load_master_json", {"schema_type": schema_type, "session_id": paths.current_session_id()}
        )
    return _toolkit_load(schema_type)
