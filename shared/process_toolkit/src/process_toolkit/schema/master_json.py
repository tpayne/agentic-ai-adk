"""Reads output/process_data.json / output/design_data.json for a consumer
(e.g. CloudArch) that doesn't necessarily know in advance whether it's
grounded against a process or a design document.
"""

import json
import os
from typing import Optional

from process_toolkit import paths

_FILENAMES = {"process": "process_data.json", "design": "design_data.json"}


def _read_json(filename: str) -> Optional[dict]:
    path = paths.output_path(filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_master_json(schema_type: Optional[str] = None) -> dict:
    """schema_type: "process" or "design" loads exactly that file (empty
    dict if it's missing/unreadable) -- use this whenever the caller
    actually knows which document it wants (e.g. the diagram's own
    provenance), rather than risking the wrong one.

    schema_type=None (default) auto-detects between whichever of the two
    files exist. If only one exists, that one wins. If both exist, the
    more recently modified one wins -- picking a fixed preference (e.g.
    always "process") would silently ground a consumer against the wrong
    document whenever a workspace has both, with no error to signal it.
    """
    if schema_type is not None:
        filename = _FILENAMES.get(schema_type)
        if filename is None:
            return {}
        return _read_json(filename) or {}

    candidates = []
    for filename in _FILENAMES.values():
        path = paths.output_path(filename)
        if os.path.exists(path):
            try:
                candidates.append((os.path.getmtime(path), filename))
            except OSError:
                continue
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0])
    _, newest_filename = candidates[-1]
    return _read_json(newest_filename) or {}
