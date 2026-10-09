"""Shared drawio XML persistence (save/load output/cloudarch_drawio.xml).

save_drawio_xml is deliberately simplified for the structured-engine-only
path this port defaults to: the heavy freehand-XML repair/shape-mapping
passes and the lock-file concurrency guard the ADK original's save side
has are dropped since build_structured_drawio_xml always emits
already-valid, already-correctly-styled XML by construction -- there is
nothing for a repair pass to fix. load_drawio_xml has no such asymmetry
(reading back whatever was last saved), so it's shared with the ADK port
via process_toolkit.drawio.persistence.
"""

import os
import xml.etree.ElementTree as ET

from coded_tools.common.paths import output_path
from process_toolkit.drawio.persistence import load_drawio_xml  # noqa: F401

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
