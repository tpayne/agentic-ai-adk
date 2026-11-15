"""Compliance guard: coded_tools/ and cli.py must never import
process_toolkit directly -- every call goes through process_interface
(shared/process_interface), the one chokepoint that decides locally vs.
via the ProcessToolkitServer MCP server per PROCESS_TOOLKIT_MODE. See
process_interface's own module docstrings for the full rationale.

This is deliberately a plain grep over import STATEMENTS, not prose --
docstrings/comments mentioning "process_toolkit" by name (there are many,
explaining what each re-exported function's logic used to live in) are
fine and expected; only `from process_toolkit...`/`import process_toolkit`
lines are a violation. tests/ itself is explicitly out of scope: test
fixtures that monkeypatch process_toolkit.paths.OUTPUT_DIR directly for
isolation (see conftest.py) are a different, accepted concern from
production agent code depending on the library directly.
"""

import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_IMPORT_LINE = re.compile(r"^\s*(from\s+process_toolkit\b|import\s+process_toolkit\b)")


def _find_violations(root: str) -> list[str]:
    violations = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if os.sep + ".venv" in dirpath or "__pycache__" in dirpath:
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            with open(path, "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, start=1):
                    if _IMPORT_LINE.match(line):
                        violations.append(f"{os.path.relpath(path, PROJECT_ROOT)}:{lineno}: {line.strip()}")
    return violations


def test_coded_tools_never_imports_process_toolkit_directly():
    violations = _find_violations(os.path.join(PROJECT_ROOT, "coded_tools"))
    assert violations == [], (
        "coded_tools/ must import process_interface, never process_toolkit directly:\n"
        + "\n".join(violations)
    )


def test_cli_never_imports_process_toolkit_directly():
    violations = []
    path = os.path.join(PROJECT_ROOT, "cli.py")
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if _IMPORT_LINE.match(line):
                violations.append(f"cli.py:{lineno}: {line.strip()}")
    assert violations == [], "cli.py must import process_interface, never process_toolkit directly:\n" + "\n".join(violations)
