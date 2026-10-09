"""Reads whichever of output/process_data.json / output/design_data.json
exists on disk (auto-detecting which one, since a consumer like CloudArch
doesn't know in advance whether it's grounded against a process or a
design document).
"""

import json
import os

from process_toolkit import paths


def load_master_json() -> dict:
    for filename in ("process_data.json", "design_data.json"):
        path = paths.output_path(filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}
