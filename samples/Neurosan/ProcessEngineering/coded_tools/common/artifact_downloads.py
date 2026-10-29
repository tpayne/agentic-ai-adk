"""Resolving and copying a generated artifact (the cloud architecture
diagram, or a generated Word document) to a local filesystem path.

The single, canonical implementation -- shared by the "list"/"download"
control lines in cli.py's own interactive/-f CLI AND the Flask artifact
routes in build_web_app (cli.py used to keep its own second,
_PROJECT_ROOT-based copy of this logic; that duplication stopped being
harmless once output/ became session-scoped, since only functions that go
through process_toolkit.paths resolve a request's own session directory
correctly) and DownloadArtifactCodedTool below (for the LLM-invokable
"download X to Y" natural-language path).
"""

import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from werkzeug.utils import safe_join

from process_toolkit import paths
from process_toolkit.iac.generation import IAC_ZIP_FILENAME, iac_zip_exists

CLOUDARCH_FILENAME = "cloudarch_drawio.xml"


def cloudarch_exists() -> bool:
    """Whether output/cloudarch_drawio.xml has been generated yet -- for
    callers (the "list" control line, download_artifact's own "nothing
    matched" message) that need to know this without reaching into
    resolve_artifact_target's own private check. Matches the ADK port's
    own identically-named artifact_downloads.cloudarch_diagram_exists."""
    return os.path.isfile(os.path.join(paths.output_dir(), CLOUDARCH_FILENAME))


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
    output_dir = paths.output_dir()
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
    output/. werkzeug's own safe_join (the library sanitizer CodeQL's
    path-injection query actually recognizes as a barrier, unlike a
    hand-rolled os.path.commonpath/startswith comparison) rejects any
    ".."/absolute-path escape before a path is ever built; the realpath
    + prefix containment check after it is still kept as defense in
    depth against a symlink planted inside output/ pointing elsewhere.
    """
    if not filename:
        return None
    output_dir = os.path.realpath(paths.output_dir())
    joined = safe_join(output_dir, os.path.basename(filename))
    if joined is None:
        return None
    candidate = os.path.realpath(joined)
    if candidate != output_dir and not candidate.startswith(output_dir + os.sep):
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate


def resolve_artifact_target(target: Optional[str]) -> Optional[str]:
    """
    Resolves a natural-language-ish `target` hint to a real filename
    currently in output/ -- for the LLM-invokable download tool, which
    (unlike a human reading "list"'s own output) doesn't necessarily
    know a generated document's own exact dynamic filename, only what
    the user asked for in plain words ("the cloud architecture diagram",
    "the document I just generated", an exact name they were told).

    - A target string containing "iac"/"terraform"/"cloudformation"/
      "pulumi"/"infrastructure"/"infra" (case-insensitive) resolves to
      the generated Infrastructure-as-Code zip, if one has been
      generated. Checked BEFORE the cloudarch-diagram check below, since
      a request like "download the IaC zip for this cloud architecture"
      legitimately contains both "iac" and "architecture" -- the IaC zip
      is unambiguously the more specific match when its own keyword is
      present.
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
    if normalized and any(word in normalized for word in ("iac", "terraform", "cloudformation", "pulumi", "infrastructure", "infra")):
        return IAC_ZIP_FILENAME if iac_zip_exists() else None
    if normalized and any(word in normalized for word in ("cloudarch", "diagram", "architecture", "xml")):
        return CLOUDARCH_FILENAME if cloudarch_exists() else None

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
