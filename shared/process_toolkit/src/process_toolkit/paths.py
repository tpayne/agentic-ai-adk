"""Single source of truth for where this library's functions write
generated artifacts (diagrams, documents). Defaults to a relative "output"
directory, matching the ADK sample's own long-standing convention -- a
caller that wants a different (e.g. absolute, test-isolated) location can
either monkeypatch OUTPUT_DIR directly (exactly how the neuro-san sample's
own test suite isolates its output/ directory per test) or pass an
explicit output_dir to the functions that accept one.
"""

import os

OUTPUT_DIR = "output"


def output_dir(*parts: str) -> str:
    """Returns (and ensures the existence of) OUTPUT_DIR/*parts as a
    directory."""
    path = os.path.join(OUTPUT_DIR, *parts)
    os.makedirs(path, exist_ok=True)
    return path


def output_path(*parts: str) -> str:
    """Returns OUTPUT_DIR/*parts as a file path, ensuring its parent
    directory exists."""
    path = os.path.join(OUTPUT_DIR, *parts)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path
