"""Always-local re-export -- never redirects to MCP mode, even when
PROCESS_TOOLKIT_MODE=mcp. Even a remote call needs a local path to write
downloaded artifact bytes to (see _artifacts.materialize), so this is pure
plumbing every other module (local or mcp branch) depends on.

OUTPUT_DIR itself is deliberately NOT re-exported as a value: it's a
mutable module global process_toolkit.paths.OUTPUT_DIR that test fixtures
monkeypatch directly, and copying its current value here at import time
would silently go stale the moment process_toolkit's own global changes.
Everything that needs the live value already goes through output_dir()/
output_path(), which read process_toolkit's own global at call time --
there is no use case in either agent app for reading the raw constant.
"""

from process_toolkit.paths import (
    SESSION_META_FILENAME,
    current_session_id,
    output_dir,
    output_path,
    sanitize_session_id,
    use_session,
)

__all__ = [
    "SESSION_META_FILENAME",
    "current_session_id",
    "output_dir",
    "output_path",
    "sanitize_session_id",
    "use_session",
]
