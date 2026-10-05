"""Reads whichever of output/process_data.json / output/design_data.json
exists on disk (auto-detecting which one, since a consumer like CloudArch
doesn't know in advance whether it's grounded against a process or a
design document).

Simplified from the ADK sample's load_master_process_json (utils.py): this
version skips the lock-wait and template-fallback machinery, which only
matter once a generation pipeline with matching write-side locking exists
to need them (see the process/design-doc pipeline port).
"""

import json
import os

from coded_tools.common.paths import output_path


def load_master_json() -> dict:
    for filename in ("process_data.json", "design_data.json"):
        path = output_path(filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}
