"""Materializes MCP-server-produced artifacts to the same local path
process_toolkit's own in-process functions would have used -- see the plan's
"artifact-materialization problem" section for why this is the chosen
approach: artifact_downloads.py (both agent apps) resolves generated files
by scanning paths.output_dir() for known extensions, never by parsing a
generation message, so "a local file exists right after generation" has to
keep being true regardless of which mode produced it.
"""

import base64
from typing import Any, Optional

from process_toolkit import paths


def materialize(documents: list[dict[str, Any]]) -> list[str]:
    """Decodes each {"filename": str, "base64": str, ...} entry and writes
    it to paths.output_path(filename). Returns the local paths written, in
    the same order as `documents`."""
    written = []
    for doc in documents:
        local_path = paths.output_path(doc["filename"])
        with open(local_path, "wb") as f:
            f.write(base64.b64decode(doc["base64"]))
        written.append(local_path)
    return written


def materialize_one(document: Optional[dict[str, Any]]) -> Optional[str]:
    """Same as materialize(), for the single-artifact tools (generate_diagram,
    zip_iac, ...) that return `{"diagram"|"workbook"|...: {...} | None}`
    rather than a `documents: [...]` list."""
    if document is None:
        return None
    return materialize([document])[0]
