"""Shared filesystem-path-component sanitizer, used by every document/
diagram generation module so they don't each re-derive their own, slightly
different `.replace(" ", "_")` version.
"""

import re

_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')


def safe_filename_component(name: str, max_len: int = 150) -> str:
    """
    Sanitizes a string for safe use as a single filesystem path component
    (a generated .docx/.png filename), on POSIX and Windows alike.

    Several generated-document save paths build their filename directly
    from a free-text document title (process_name, or
    document_metadata.title/system_name for a design document), previously
    via nothing more than `name.replace(' ', '_')`. That leaves any other
    filesystem-reserved character untouched -- most importantly "/", which
    silently turns into an unintended, nonexistent subdirectory rather
    than part of the filename (e.g. a real title containing
    "... SAM/HAM Assets" produced a save path with a "SAM" directory that
    was never created, raising FileNotFoundError at doc.save() time
    instead of just being an unusual-looking filename).

    This replaces path separators and the other Windows-reserved filename
    characters (\\ / : * ? " < > |) with underscores, collapses whitespace
    to underscores, strips leading/trailing dots and underscores, and caps
    the length so a very long generated title can't hit filesystem
    path-length limits either. Falls back to "untitled" for empty/non-
    string input. A generated title/step name is untrusted content; a bare
    .replace(" ", "_") leaves "/" and ".." untouched, which could otherwise
    escape the intended output directory entirely.
    """
    if not isinstance(name, str) or not name.strip():
        return "untitled"
    collapsed = re.sub(r"\s+", "_", name.strip())
    safe = _UNSAFE_FILENAME_CHARS.sub("_", collapsed)
    safe = safe.strip("._") or "untitled"
    return safe[:max_len]
