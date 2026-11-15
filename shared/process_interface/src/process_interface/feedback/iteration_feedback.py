"""Switchable -- every function here reads or writes a review-feedback
mailbox or approval-state file in the session's own output directory, so
all five follow PROCESS_TOOLKIT_MODE. Approval state is kept on the same
side as document generation deliberately (see the plan's "feedback =
switchable" reasoning): if docgen is remoted but approval state stayed
local, a reviewer's sign-off could get out of sync with which side
actually holds the document it's signing off on.
"""

from typing import Any, Dict, Optional, Sequence

from process_toolkit.feedback import iteration_feedback as _toolkit

from process_interface import config, paths, _transport

__all__ = [
    "load_iteration_feedback",
    "save_iteration_feedback",
    "reset_approval_state",
    "reset_feedback_channels",
    "format_review_status_summary",
]


def load_iteration_feedback(reset_data: bool = True, channel: str = "") -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call(
            "load_feedback",
            {"reset_data": reset_data, "channel": channel, "session_id": paths.current_session_id()},
        )
    return _toolkit.load_iteration_feedback(reset_data=reset_data, channel=channel)


def save_iteration_feedback(feedback_data: Any, channel: str = "") -> str:
    if config.is_mcp_mode():
        result = _transport.call(
            "save_feedback",
            {"feedback_data": feedback_data, "channel": channel, "session_id": paths.current_session_id()},
        )
        return result["message"]
    return _toolkit.save_iteration_feedback(feedback_data, channel=channel)


def reset_approval_state() -> None:
    if config.is_mcp_mode():
        _transport.call("reset_approval_state", {"session_id": paths.current_session_id()})
        return
    _toolkit.reset_approval_state()


def reset_feedback_channels() -> None:
    if config.is_mcp_mode():
        _transport.call("reset_feedback_channels", {"session_id": paths.current_session_id()})
        return
    _toolkit.reset_feedback_channels()


def format_review_status_summary(channels: Optional[Sequence[str]] = None) -> str:
    if config.is_mcp_mode():
        args: Dict[str, Any] = {"session_id": paths.current_session_id()}
        if channels is not None:
            args["channels"] = list(channels)
        return _transport.call("review_status_summary", args)
    if channels is None:
        return _toolkit.format_review_status_summary()
    return _toolkit.format_review_status_summary(channels)
