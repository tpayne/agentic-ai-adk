"""Always-local re-export -- validate_iac_files takes a dict of filename to
content already in hand and returns a structural report; no disk I/O,
unlike iac/generation.py's save/load/zip functions (a later phase), which
read and write the session's own IaC files on disk."""

from process_toolkit.iac.validation import validate_iac_files

__all__ = ["validate_iac_files"]
