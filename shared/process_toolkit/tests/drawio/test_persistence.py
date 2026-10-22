"""reset_drawio_xml is the primitive both ports' CloudArch pipelines use
to guarantee a chat session's first touch of the cloud architecture
subsystem never silently inherits a diagram a different, unrelated
session left behind on disk -- see process_agents.cloudarch.
cloudarch_pipeline_agent (ADK) / coded_tools.cloudarch.
reset_loop_state_tool (neuro-san)."""

import os

from process_toolkit import paths
from process_toolkit.drawio.persistence import (
    DRAWIO_FILENAME,
    DRAWIO_LOCK_FILENAME,
    DRAWIO_RAW_FILENAMES,
    load_drawio_xml,
    reset_drawio_xml,
)


def test_reset_removes_the_diagram_and_its_lock_and_raw_dump_siblings():
    for name in (DRAWIO_FILENAME, DRAWIO_LOCK_FILENAME, *DRAWIO_RAW_FILENAMES):
        with open(paths.output_path(name), "w", encoding="utf-8") as f:
            f.write("content")

    reset_drawio_xml()

    for name in (DRAWIO_FILENAME, DRAWIO_LOCK_FILENAME, *DRAWIO_RAW_FILENAMES):
        assert not os.path.exists(paths.output_path(name))

    assert load_drawio_xml() == {"status": "NOT_FOUND", "xml": None}


def test_reset_is_a_safe_no_op_when_nothing_exists():
    reset_drawio_xml()  # must not raise
    assert load_drawio_xml() == {"status": "NOT_FOUND", "xml": None}
