"""save_iac_files is switchable: in MCP mode it both persists the files
on the server AND writes them locally -- no base64/materialize step is
needed for the write side specifically because the caller already has
the actual file content in hand (it's the `files` argument itself), so
there's nothing to fetch back from the server.

load_iac_files/zip_iac_files/iac_zip_exists stay always-local: they read
the local mirror save_iac_files just wrote, which is (by construction)
identical to whatever the server has, so there's no reason to pay a
network round trip to re-read it. validate_iac_files already lives in
iac/validation.py (Phase 1) as a pure, always-local function.
"""

from typing import Dict

from process_toolkit.iac.generation import IAC_ZIP_FILENAME, iac_zip_exists, load_iac_files, zip_iac_files
from process_toolkit.iac.generation import save_iac_files as _toolkit_save_iac_files

from process_interface import config, paths, _transport

__all__ = ["IAC_ZIP_FILENAME", "iac_zip_exists", "load_iac_files", "zip_iac_files", "save_iac_files"]


def save_iac_files(files: Dict[str, str]) -> Dict[str, str]:
    if config.is_mcp_mode():
        _transport.call("save_iac", {"files": files, "session_id": paths.current_session_id()})
    # Local mirror, always -- in local mode this IS the save; in mcp mode
    # it's the mirror load_iac_files/zip_iac_files read back afterward.
    return _toolkit_save_iac_files(files)
