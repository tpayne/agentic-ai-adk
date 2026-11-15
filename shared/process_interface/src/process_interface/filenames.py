"""Always-local re-export -- pure string sanitization, no I/O, no reason to
ever call this remotely."""

from process_toolkit.filenames import safe_filename_component

__all__ = ["safe_filename_component"]
