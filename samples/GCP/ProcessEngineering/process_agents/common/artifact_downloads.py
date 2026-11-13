"""Resolving and copying a generated artifact (the cloud architecture
diagram, or a generated Word document) to a local filesystem path.

Developed in tandem with the neuro-san port's own
coded_tools/common/artifact_downloads.py -- same contract, same
resolution rules, both now resolved through process_toolkit.paths (this
port used to keep its own independent PROJECT_ROOT/output/ convention;
that stopped being harmless once output/ became session-scoped, since
only functions that go through process_toolkit.paths resolve a request's
own session directory correctly -- see paths.py's own use_session()
docstring).

Shared by this project's own "list"/"download" control lines
(start_local_chat/process_file in .agent) and download_artifact in
.utils_agent (the LLM-invokable natural-language path, registered as a
root_agent tool).
"""

import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from werkzeug.utils import safe_join

from process_toolkit import paths as toolkit_paths
from process_toolkit.iac.generation import IAC_ZIP_FILENAME, iac_zip_exists
from process_toolkit.portfolio_backlog.portfolio_backlog import PORTFOLIO_BACKLOG_WORKBOOK_FILENAME

CLOUDARCH_FILENAME = "cloudarch_drawio.xml"


def cloudarch_diagram_exists() -> bool:
    """Whether output/cloudarch_drawio.xml has been generated yet -- for
    callers (download_artifact's own "nothing matched" message) that need
    to know this without reaching into toolkit_paths.output_dir()
    themselves."""
    return os.path.isfile(os.path.join(toolkit_paths.output_dir(), CLOUDARCH_FILENAME))


def portfolio_backlog_workbook_exists() -> bool:
    """Whether the generated Enterprise Agile Portfolio Backlog workbook is available."""
    return os.path.isfile(os.path.join(toolkit_paths.output_dir(), PORTFOLIO_BACKLOG_WORKBOOK_FILENAME))


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
    output_dir = toolkit_paths.output_dir()
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
    output_dir = os.path.realpath(toolkit_paths.output_dir())
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
    currently in output/ -- for the LLM-invokable download_artifact tool,
    which (unlike a human reading "list"'s own output) doesn't
    necessarily know a generated document's own exact dynamic filename,
    only what the user asked for in plain words ("the cloud architecture
    diagram", "the document I just generated", an exact name they were
    told).

    - A target string containing "iac"/"terraform"/"cloudformation"/
      "pulumi"/"infrastructure"/"infra" (case-insensitive) resolves to
      the generated Infrastructure-as-Code zip, if one has been
      generated. Checked BEFORE the cloudarch-diagram check below, since
      a request like "download the IaC zip for this cloud architecture"
      legitimately contains both "iac" and "architecture" -- the IaC zip
      is unambiguously the more specific match when its own keyword is
      present.
    - A target mentioning "backlog", "WSJF", or the portfolio backlog
      workbook filename resolves to that workbook, if it has been generated.
    - If the target expresses document intent ("doc" as a whole word --
      NOT a substring, so "docker" doesn't false-positive --, "document",
      "docx", "word", "vision", "definition", "hld"/"lld" as whole words,
      or "high-level design"/"low-level design" in either spacing) or
      matches an existing generated Word document, it resolves to that
      document.
    - A target string indicating a diagram ("cloudarch", "diagram",
      "drawio", "xml", or "architecture" as a substring -- CONFIRMED AS A
      REAL BUG: an earlier version of this check required "architecture"
      to be the ENTIRE normalized string, or one of two other fixed
      phrases, so "can I get the architecture now" or "the cloud
      architecture" resolved to nothing even with a diagram on disk)
      resolves to the cloud architecture diagram, if one has been
      generated.
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
    if normalized and any(word in normalized for word in ("backlog", "wsjf", PORTFOLIO_BACKLOG_WORKBOOK_FILENAME)):
        return (
            PORTFOLIO_BACKLOG_WORKBOOK_FILENAME
            if portfolio_backlog_workbook_exists()
            else None
        )

    docs = list_output_documents()
    normalized_words = set(normalized.split())
    # "doc"/"hld"/"lld" are checked as WHOLE WORDS, not substrings -- "doc" as a substring
    # false-positives on "docker" (CONFIRMED AS A REAL BUG: "show me the docker architecture
    # diagram" incorrectly matched is_doc_intent via "doc" in "docker", routing a clear
    # diagram request into the document-matching branch). "document"/"docx"/"word"/"vision"/
    # "definition" are long/specific enough that substring matching is safe. Spelled-out
    # "high-level design"/"low-level design" (either hyphenated or spaced) are also doc
    # intent -- the abbreviations alone aren't the only way a user names these documents.
    is_doc_intent = (
        any(word in normalized for word in ("document", "docx", "word", "vision", "definition"))
        or bool(normalized_words & {"doc", "hld", "lld"})
        or any(phrase in normalized for phrase in ("high-level design", "high level design", "low-level design", "low level design"))
    )

    # If document intent is not explicitly expressed, check for diagram requests.
    # "architecture" is a plain substring check (not an exact-phrase match) -- CONFIRMED AS A
    # REAL BUG: an earlier version required normalized to EQUAL "architecture"/"cloud
    # architecture"/"the architecture" exactly, so "can I get the architecture now" or even
    # "the cloud architecture" (a fourth, very natural phrasing matching none of those three)
    # resolved to nothing despite a real generated diagram existing. Safe to widen back to a
    # substring check here specifically because this whole branch is already gated on
    # `not is_doc_intent` -- a document-shaped request (containing "document"/"vision"/etc.)
    # never reaches this branch regardless of whether it also happens to contain "architecture".
    if normalized and not is_doc_intent:
        if any(word in normalized for word in ("cloudarch", "diagram", "drawio", "xml", "architecture")):
            return CLOUDARCH_FILENAME if cloudarch_diagram_exists() else None

    if not normalized:
        return docs[0]["filename"] if docs else None

    # Check for document matches
    for doc in docs:
        fn_lower = doc["filename"].lower()
        fn_clean = fn_lower.replace("_", " ")
        fn_stem = os.path.splitext(fn_clean)[0]
        if (
            normalized == fn_lower
            or normalized in fn_lower
            or normalized in fn_clean
            or normalized.replace(" ", "_") in fn_lower
            or fn_lower in normalized
            or fn_stem in normalized
        ):
            return doc["filename"]

    # Strip common filler words to check if meaningful keywords match a document
    meaningful = " ".join([w for w in normalized.split() if w not in ("the", "a", "an", "document", "doc", "docx", "file", "word")])
    if meaningful:
        for doc in docs:
            fn_clean = doc["filename"].lower().replace("_", " ")
            if meaningful in fn_clean or meaningful.replace(" ", "_") in doc["filename"].lower():
                return doc["filename"]

    # Semantic variant match if specific doc keywords are in the target
    if is_doc_intent and docs:
        if "vision" in normalized:
            for doc in docs:
                if "vision" in doc["filename"].lower():
                    return doc["filename"]
        if "definition" in normalized:
            for doc in docs:
                if "definition" in doc["filename"].lower():
                    return doc["filename"]
        if "hld" in normalized_words or "high-level design" in normalized or "high level design" in normalized:
            for doc in docs:
                if "hld" in doc["filename"].lower():
                    return doc["filename"]
        if "lld" in normalized_words or "low-level design" in normalized or "low level design" in normalized:
            for doc in docs:
                if "lld" in doc["filename"].lower():
                    return doc["filename"]
        if len(docs) == 1:
            return docs[0]["filename"]

    # Fallback to diagram check if not matched as a doc and contains diagram keywords
    if normalized and any(word in normalized for word in ("cloudarch", "diagram", "drawio", "xml", "architecture")):
        return CLOUDARCH_FILENAME if cloudarch_diagram_exists() else None

    return None


def copy_artifact_to_destination(filename: str, destination: str) -> str:
    """
    Copies `filename` (resolved via safe_output_file_path -- must already
    be a real file in output/) to `destination`. Existing directories,
    paths with a trailing separator, and paths without a filename
    extension are treated as directories and created if needed; the file
    keeps its own basename there. A path with an extension is treated as
    a target file path. Returns the absolute final path copied to.

    Raises ValueError if `filename` doesn't resolve to a real file inside
    output/ (including a path-traversal attempt); propagates any OSError
    the copy itself raises for the caller to report in its own idiom.
    """
    source_path = safe_output_file_path(filename)
    if source_path is None:
        raise ValueError(f"No generated file named '{filename}' in output/.")
    raw_destination = _normalize_download_destination(destination)
    has_trailing_separator = raw_destination.endswith(os.sep) or (
        os.altsep is not None and raw_destination.endswith(os.altsep)
    )
    destination = os.path.abspath(raw_destination)
    destination_name = os.path.basename(os.path.normpath(destination))
    is_directory = (
        os.path.isdir(destination)
        or has_trailing_separator
        or not os.path.splitext(destination_name)[1]
    )
    if is_directory:
        if os.path.exists(destination) and not os.path.isdir(destination):
            raise ValueError(f"Destination '{destination}' is a file, not a directory.")
        os.makedirs(destination, exist_ok=True)
        dest_path = os.path.join(destination, os.path.basename(source_path))
    else:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        dest_path = destination
    shutil.copy2(source_path, dest_path)
    return dest_path


def _normalize_download_destination(destination: str) -> str:
    """Map a natural Downloads-folder request to the user's home Downloads."""
    raw_destination = os.path.expanduser((destination or ".").strip())
    alias = raw_destination.casefold().strip().rstrip("/\\")
    if alias in {
        "download folder",
        "downloads folder",
        "download directory",
        "downloads directory",
        "the downloads folder",
        "the downloads directory",
        "my downloads folder",
        "my downloads directory",
    }:
        return os.path.join(os.path.expanduser("~"), "Downloads")

    normalized_parts = os.path.normpath(raw_destination).replace("\\", "/").casefold().split("/")
    if not os.path.isabs(raw_destination) and normalized_parts[-2:] == ["output", "downloads"]:
        return os.path.join(os.path.expanduser("~"), "Downloads")
    return raw_destination
