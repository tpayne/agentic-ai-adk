"""Persists generator-produced Infrastructure-as-Code (IaC) files for the
current session's cloud architecture diagram, and zips them into a single
downloadable archive.

The generating agent writes the actual IaC content itself (same division
of labor as every other generator in this project -- the LLM reasons/
writes, the CodedTool only persists exactly what it's given, no server-
side re-derivation); this module is purely the persistence/packaging
layer, mirroring docgen's own "the agent writes, output_path() says
where" split.
"""

import os
import zipfile
from typing import Dict

from process_toolkit import paths
from process_toolkit.filenames import safe_filename_component

IAC_SUBDIR = "iac"
IAC_ZIP_FILENAME = "cloudarch_iac.zip"


def save_iac_files(files: Dict[str, str]) -> Dict[str, str]:
    """Persists `files` ({relative_filename: content}) into
    output/<session>/iac/, overwriting any previous IaC generation for
    this session first -- so regenerating in a different language (or
    revising after a failed validation pass) never leaves stale files
    from an earlier attempt mixed in with the new ones.

    Each relative filename is sanitized ONE PATH COMPONENT AT A TIME via
    safe_filename_component (never trusting an LLM-supplied filename with
    ".."/an absolute path outright), while still allowing a single level
    of subdirectory structure (e.g. "modules/vpc/main.tf") since real IaC
    projects commonly use one.

    Returns {sanitized_relative_filename: absolute_path_written}.
    """
    iac_dir = paths.output_dir(IAC_SUBDIR)
    for root, _dirs, filenames in os.walk(iac_dir):
        for name in filenames:
            os.remove(os.path.join(root, name))

    written: Dict[str, str] = {}
    for raw_name, content in files.items():
        parts = [
            safe_filename_component(part)
            for part in str(raw_name).replace("\\", "/").split("/")
            if part not in ("", ".", "..")
        ]
        if not parts:
            continue
        rel_name = "/".join(parts)
        dest_path = os.path.join(iac_dir, *parts)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else str(content))
        written[rel_name] = dest_path
    return written


def load_iac_files() -> Dict[str, str]:
    """Reads back every file currently under output/<session>/iac/, keyed
    by its path relative to that directory (matching save_iac_files's own
    key shape) -- used by the validator agent/step so it always re-reads
    what was actually persisted rather than trusting its own tool-call
    argument echoed back to it."""
    iac_dir = paths.output_dir(IAC_SUBDIR)
    files: Dict[str, str] = {}
    for root, _dirs, filenames in os.walk(iac_dir):
        for name in filenames:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, iac_dir).replace(os.sep, "/")
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                files[rel] = f.read()
    return files


def zip_iac_files() -> str:
    """Zips the current session's output/<session>/iac/ directory into
    output/<session>/cloudarch_iac.zip, overwriting any previous zip for
    this session. Returns the zip's own path.

    Raises FileNotFoundError if no IaC files have been generated yet this
    session -- there is deliberately no "zip an empty archive" fallback;
    an empty/missing zip would look like success to a caller that only
    checks "did this raise," silently handing the user a useless file.
    """
    iac_dir = paths.output_dir(IAC_SUBDIR)
    entries = []
    for root, _dirs, filenames in os.walk(iac_dir):
        for name in filenames:
            full = os.path.join(root, name)
            arcname = os.path.relpath(full, iac_dir)
            entries.append((full, arcname))
    if not entries:
        raise FileNotFoundError("No IaC files have been generated yet -- nothing to zip.")

    zip_path = paths.output_path(IAC_ZIP_FILENAME)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for full, arcname in sorted(entries):
            zf.write(full, arcname)
    return zip_path


def iac_zip_exists() -> bool:
    return os.path.exists(paths.output_path(IAC_ZIP_FILENAME))
