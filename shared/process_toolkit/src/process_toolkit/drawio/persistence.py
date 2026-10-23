"""Shared drawio XML *read* side (output/cloudarch_drawio.xml).

The write side is deliberately NOT shared: ADK's save_drawio/
save_drawio_structured include a lock-file concurrency guard and (for
save_drawio specifically) a large provider-aware shape/container mapping
pass for freehand LLM-authored XML -- real capabilities the neuro-san
port's structured-engine-only save_drawio_xml was never designed to need.
Reading back whatever was last saved has no such asymmetry, so it's
shared here.
"""

import logging
import os

from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.DrawioPersistence")

DRAWIO_FILENAME = "cloudarch_drawio.xml"
# ADK-only siblings (concurrency lock + malformed-XML debug dumps -- see
# this module's own docstring on why the write side isn't shared); the
# neuro-san port never creates them, so removing them there is always a
# harmless no-op.
DRAWIO_LOCK_FILENAME = ".cloudarch_drawio.lock"
DRAWIO_RAW_FILENAMES = ("cloudarch_drawio_raw.xml", "cloudarch_drawio_mapped_raw.xml")


def load_drawio_xml() -> dict:
    path = paths.output_path(DRAWIO_FILENAME)
    if not os.path.exists(path):
        return {"status": "NOT_FOUND", "xml": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {"status": "OK", "xml": f.read()}
    except Exception as e:
        # The caller gets the error message back in the returned dict,
        # but that alone leaves no trace in this process's own logs --
        # a recurring read failure (permissions, disk issues) was
        # otherwise invisible server-side.
        logger.error("Failed to read %s: %s", path, e, exc_info=True)
        return {"status": "ERROR", "xml": None, "error": str(e)}


def reset_drawio_xml() -> None:
    """Removes any existing cloud-architecture diagram, plus its
    concurrency-lock and malformed-XML debug-dump siblings. Callers use
    this to guarantee a chat session's first touch of the cloud
    architecture subsystem never silently inherits a diagram a
    different, unrelated session left behind on disk -- see
    process_agents.cloudarch.cloudarch_pipeline_agent (ADK) /
    coded_tools.cloudarch.reset_loop_state_tool (neuro-san), and
    coded_tools.cloudarch.load_drawio_tool for why a read-only query must
    NOT call this."""
    for name in (DRAWIO_FILENAME, DRAWIO_LOCK_FILENAME, *DRAWIO_RAW_FILENAMES):
        path = paths.output_path(name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.warning("Failed to remove stale %s: %s", path, e, exc_info=True)
