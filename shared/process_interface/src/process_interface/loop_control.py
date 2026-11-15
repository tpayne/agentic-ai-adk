"""Always-local re-export -- NEVER redirects to MCP mode, by explicit user
decision: the generate/review loop's iteration counter and approval-state
files live alongside this process's own pipeline lock, not as an
independent remote concern."""

from process_toolkit.loop_control import (
    APPROVAL_FILENAME,
    STOP_COUNTER_FILENAME,
    evaluate_loop_stop,
    load_approval_state,
    load_counter,
    reset_counter,
    save_counter,
)

__all__ = [
    "APPROVAL_FILENAME",
    "STOP_COUNTER_FILENAME",
    "evaluate_loop_stop",
    "load_approval_state",
    "load_counter",
    "reset_counter",
    "save_counter",
]
