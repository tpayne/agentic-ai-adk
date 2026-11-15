"""Always-local re-export -- NEVER redirects to MCP mode, by explicit user
decision: a mutex protecting this process's own working directory doesn't
make sense as a remote call, and the acquire/heartbeat/release sequence is
stateful across multiple calls in a way a stateless RPC can't represent
cleanly. tests/test_always_local.py asserts this module never imports
process_interface._transport."""

from process_toolkit.run_lock import (
    LOCK_FILENAME,
    PipelineLockedError,
    acquire_pipeline_lock,
    force_clear_pipeline_lock,
    peek_pipeline_lock,
    release_pipeline_lock,
    start_pipeline_lock_heartbeat,
    stop_pipeline_lock_heartbeat,
)

__all__ = [
    "LOCK_FILENAME",
    "PipelineLockedError",
    "acquire_pipeline_lock",
    "force_clear_pipeline_lock",
    "peek_pipeline_lock",
    "release_pipeline_lock",
    "start_pipeline_lock_heartbeat",
    "stop_pipeline_lock_heartbeat",
]
