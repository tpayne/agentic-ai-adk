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

import logging
import os
import xml.etree.ElementTree as ET

from process_toolkit.drawio.persistence import load_drawio_xml  # noqa: F401
from process_toolkit.paths import output_path

logger = logging.getLogger("ProcessArchitect.DrawioPersistence")

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
            # Purely an optimization (skip an unnecessary identical
            # rewrite) -- falling through to the unconditional write
            # below is still correct either way, but a silently
            # recurring failure here (e.g. a permissions issue) was
            # previously invisible with zero trace.
            logger.debug("Could not compare existing %s for the no-op-write check.", path, exc_info=True)

    with open(path, "w", encoding="utf-8") as f:
        f.write(xml_content)
    return {"status": "OK", "message": f"The file {path} was saved successfully."}
