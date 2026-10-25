"""Resolving and copying a generated artifact (the cloud architecture
diagram, or a generated Word document) to a local filesystem path.

Developed in tandem with the neuro-san port's own
coded_tools/common/artifact_downloads.py -- same contract, same
resolution rules, adapted to this port's own PROJECT_ROOT/output/
convention instead of process_toolkit.paths' CWD-relative one.

Shared by this project's own "list"/"download" control lines
(start_local_chat/process_file in .agent) and download_artifact in
.utils_agent (the LLM-invokable natural-language path, registered as a
root_agent tool). PROJECT_ROOT is computed independently here (not
imported from .utils_agent) so utils_agent can import FROM this module
(for download_artifact) without the two forming an import cycle.
"""

import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLOUDARCH_FILENAME = "cloudarch_drawio.xml"


def _output_dir() -> str:
    path = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(path, exist_ok=True)
    return path


def cloudarch_diagram_exists() -> bool:
    """Whether output/cloudarch_drawio.xml has been generated yet -- for
    callers (download_artifact's own "nothing matched" message) that need
    to know this without reaching into this module's own private
    _output_dir()."""
    return os.path.isfile(os.path.join(_output_dir(), CLOUDARCH_FILENAME))


def list_output_documents() -> List[Dict[str, Any]]:
    """
    Every generated .docx currently sitting in output/. There is no
    fixed, predictable filename for these -- each one is named after
    whatever process/design name was actually generated (see
    process_toolkit.docgen.generation's own safe_filename_component(name)
    + ".docx") -- so "what documents exist" has to be an actual directory
    listing. Sorted most-recently-modified first -- the document someone
    just generated is the one a vague "the document"/"it" reference is
    almost always asking about.
    """
    output_dir = _output_dir()
    entries: List[Dict[str, Any]] = []
    for name in os.listdir(output_dir):
        full_path = os.path.join(output_dir, name)
        if not name.lower().endswith(".docx") or not os.path.isfile(full_path):
            continue
        stat = os.stat(full_path)
        entries.append({
            "filename": name,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    entries.sort(key=lambda e: e["modified"], reverse=True)
    return entries


def safe_output_file_path(filename: str) -> Optional[str]:
    """
    Resolves `filename` (a bare basename) to a real file strictly INSIDE
    output/, or None if it doesn't exist or would resolve outside
    output/ -- os.path.basename() discards any directory component the
    caller supplied, and the realpath + prefix containment check after
    it is what actually rules out anything cleverer (a symlink inside
    output/ pointing elsewhere, odd path encodings) rather than trusting
    a single string transform to have covered every case. The trailing
    os.sep on the prefix matters: without it, an output_dir of "/x/out"
    would wrongly accept a sibling like "/x/output_other".
    """
    if not filename:
        return None
    output_dir = os.path.realpath(_output_dir())
    candidate = os.path.realpath(os.path.join(output_dir, os.path.basename(filename)))
    if candidate != output_dir and not candidate.startswith(output_dir + os.sep):
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate


def resolve_artifact_target(target: Optional[str]) -> Optional[str]:
    """
    Resolves a natural-language-ish `target` hint to a real filename
    currently in output/ -- for the LLM-invokable download_artifact tool,
    which (unlike a human reading "list"'s own output) doesn't
    necessarily know a generated document's own exact dynamic filename,
    only what the user asked for in plain words ("the cloud architecture
    diagram", "the document I just generated", an exact name they were
    told).

    - A target string containing "cloudarch"/"diagram"/"architecture"/
      "xml" (case-insensitive) resolves to the cloud architecture
      diagram, if one has been generated.
    - A target matching an existing document's filename exactly, or as a
      case-insensitive substring, resolves to that document.
    - An empty/None target resolves to the most-recently-generated
      document (list_output_documents's own sort order) -- "the
      document"/"it" with no other context.
    - Anything else (a target that matched NOTHING) returns None rather
      than silently guessing a different file -- a wrong download is
      worse than an honest "I couldn't find that."
    """
    normalized = (target or "").strip().lower()
    if normalized and any(word in normalized for word in ("cloudarch", "diagram", "architecture", "xml")):
        cloudarch_path = os.path.join(_output_dir(), CLOUDARCH_FILENAME)
        return CLOUDARCH_FILENAME if os.path.isfile(cloudarch_path) else None

    docs = list_output_documents()
    if not normalized:
        return docs[0]["filename"] if docs else None
    for doc in docs:
        if normalized == doc["filename"].lower() or normalized in doc["filename"].lower():
            return doc["filename"]
    return None


def copy_artifact_to_destination(filename: str, destination: str) -> str:
    """
    Copies `filename` (resolved via safe_output_file_path -- must already
    be a real file in output/) to `destination`, which may be an existing
    directory (the file keeps its own basename) or a full target file
    path. Returns the actual final path copied to.

    Raises ValueError if `filename` doesn't resolve to a real file inside
    output/ (including a path-traversal attempt); propagates any OSError
    the copy itself raises (e.g. an unwritable/nonexistent destination
    directory) uncaught, for the caller to report in its own idiom.
    """
    source_path = safe_output_file_path(filename)
    if source_path is None:
        raise ValueError(f"No generated file named '{filename}' in output/.")
    destination = os.path.expanduser(destination or ".")
    dest_path = (
        os.path.join(destination, os.path.basename(source_path))
        if os.path.isdir(destination)
        else destination
    )
    shutil.copy2(source_path, dest_path)
    return dest_path
