"""Shared filesystem-path-component sanitizer, ported verbatim from the ADK
sample's safe_filename_component (utils.py). Factored out of
subprocess_json.py (its original home in this port) so the document/diagram
generation modules can reuse the exact same logic instead of each re-defining
their own, slightly different `.replace(" ", "_")` version -- which is
exactly the kind of drift the ADK original had across its own several
callers before it was centralized there.
"""

import re

_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')


def safe_filename_component(name: str, max_len: int = 150) -> str:
    """Sanitizes a string for safe use as a single filesystem path
    component, on POSIX and Windows alike. A generated title/step name is
    untrusted content; a bare .replace(" ", "_") leaves "/" and ".."
    untouched, which could otherwise escape the intended output directory
    entirely."""
    if not isinstance(name, str) or not name.strip():
        return "untitled"
    collapsed = re.sub(r"\s+", "_", name.strip())
    safe = _UNSAFE_FILENAME_CHARS.sub("_", collapsed)
    safe = safe.strip("._") or "untitled"
    return safe[:max_len]
