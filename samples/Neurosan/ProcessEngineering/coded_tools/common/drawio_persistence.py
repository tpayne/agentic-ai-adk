"""Shared drawio XML persistence (save/load output/cloudarch_drawio.xml).

Ported from the ADK sample's _save_drawio_core/load_drawio (utils.py), but
deliberately simplified for the structured-engine-only path this port
defaults to: the heavy freehand-XML repair/shape-mapping passes
(_validate_and_repair_mxgraph, _apply_shape_mappings) and the lock-file
concurrency guard are dropped since build_structured_drawio_xml always
emits already-valid, already-correctly-styled XML by construction -- there
is nothing for a repair pass to fix. Basic well-formedness parsing and the
unchanged-file no-op skip are kept.
"""

import os
import xml.etree.ElementTree as ET

from coded_tools.common.paths import output_path

DRAWIO_FILENAME = "cloudarch_drawio.xml"


def save_drawio_xml(xml_content: str) -> dict:
    path = output_path(DRAWIO_FILENAME)

    try:
        ET.fromstring(xml_content)
    except Exception as e:
        return {"status": "ERROR", "error": f"Invalid XML provided: {e}"}

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as existing:
                if existing.read().strip() == xml_content.strip():
                    return {"status": "OK", "message": f"The file {path} is unchanged."}
        except Exception:
            pass

    with open(path, "w", encoding="utf-8") as f:
        f.write(xml_content)
    return {"status": "OK", "message": f"The file {path} was saved successfully."}


def load_drawio_xml() -> dict:
    path = output_path(DRAWIO_FILENAME)
    if not os.path.exists(path):
        return {"status": "NOT_FOUND", "xml": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {"status": "OK", "xml": f.read()}
    except Exception as e:
        return {"status": "ERROR", "xml": None, "error": str(e)}
