"""Regression test for a real bug: a process-generation request whose
Analysis_Agent ended up calling load_directory_context with an invalid/
relative directory argument (e.g. "." after a bad path) resolved straight
back to THIS project's own root -- silently returning its own README.md/
BUSINESS-CASES.md as if they were genuine user-supplied source material,
with no error at all. The generated process_data.json cited "README.md"/
"BUSINESS-CASES.md" as requirement sources, and the design it produced
described the process-engineering tool itself rather than anything the
user actually asked for.

The fix lives in process_toolkit's shared load_directory_context (see
_agent_toolkit_root there): it now refuses to read a directory that
resolves to AGENT_TOOL_PATH's own parent (the project root every one of
this suite's entry points sets AGENT_TOOL_PATH to <project_root>/coded_tools
before any CodedTool loads -- see cli.py). This test exercises that guard
through this project's own real AGENT_TOOL_PATH/coded_tools wiring, not a
synthetic one, so it would have caught the original bug directly.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Same pattern this project's other tests use (test_hocon_agent_messages.py,
# test_pipeline_middleware.py, ...): AGENT_TOOL_PATH is normally set by
# cli.py/`ns chat`/`ns run` before any CodedTool loads, none of which run
# here, so a bare test import must set it itself rather than relying on
# another test module having already done so as a side effect.
os.environ.setdefault("AGENT_TOOL_PATH", str(PROJECT_ROOT / "coded_tools"))

from coded_tools.process.load_directory_context_tool import LoadDirectoryContextCodedTool  # noqa: E402


def test_project_root_actually_has_the_files_the_bug_leaked():
    # Sanity check that this project really does have these files at its
    # root -- otherwise this test would not actually reproduce the bug.
    assert (PROJECT_ROOT / "README.md").is_file()
    assert (PROJECT_ROOT / "BUSINESS-CASES.md").is_file()


def test_dot_directory_resolves_to_project_root_but_is_refused():
    assert os.environ.get("AGENT_TOOL_PATH") == str(PROJECT_ROOT / "coded_tools")

    old_cwd = os.getcwd()
    os.chdir(PROJECT_ROOT)
    try:
        result = LoadDirectoryContextCodedTool().invoke({"directory": "."}, {})
    finally:
        os.chdir(old_cwd)

    assert result["status"] == "ERROR"
    assert "files_processed" not in result
    assert "README" not in result.get("error", "")


def test_a_real_sibling_directory_still_works_normally():
    # The guard must not be so broad that it blocks legitimate directories
    # that merely happen to live near the project.
    sibling = PROJECT_ROOT.parent / "_not_the_project_root_test_dir"
    sibling.mkdir(exist_ok=True)
    try:
        (sibling / "notes.txt").write_text("Vendor onboarding requires KYC checks.")
        result = LoadDirectoryContextCodedTool().invoke({"directory": str(sibling)}, {})
    finally:
        (sibling / "notes.txt").unlink(missing_ok=True)
        sibling.rmdir()

    assert result["status"] == "OK"
    assert "KYC checks" in result["combined_text"]
