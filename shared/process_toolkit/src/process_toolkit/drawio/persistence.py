"""Shared drawio XML *read* side (output/cloudarch_drawio.xml).

The write side is deliberately NOT shared: ADK's save_drawio/
save_drawio_structured include a lock-file concurrency guard and (for
save_drawio specifically) a large provider-aware shape/container mapping
pass for freehand LLM-authored XML -- real capabilities the neuro-san
port's structured-engine-only save_drawio_xml was never designed to need.
Reading back whatever was last saved has no such asymmetry, so it's
shared here.
"""

import os

from process_toolkit import paths

DRAWIO_FILENAME = "cloudarch_drawio.xml"


def load_drawio_xml() -> dict:
    path = paths.output_path(DRAWIO_FILENAME)
    if not os.path.exists(path):
        return {"status": "NOT_FOUND", "xml": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {"status": "OK", "xml": f.read()}
    except Exception as e:
        return {"status": "ERROR", "xml": None, "error": str(e)}
