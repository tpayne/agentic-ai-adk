"""The generate/review loop's feedback mailbox + cumulative approval state.

Ported from the ADK sample's save_iteration_feedback/load_iteration_feedback
(utils.py) and the approval-state file shape _build_stop_if_ready reads
(utils_agent.py). Nothing here is ADK-specific -- it was always just plain
file I/O; only the orchestration that decides WHEN to call these (a
front-man's own instructions here, vs. ADK's LoopAgent there) differs. See
loop_control.py for the piece that WAS ADK-specific (tool_context.actions.
escalate) and its replacement.
"""

import json
import os
from typing import Any, Dict

from process_toolkit.paths import output_path

FEEDBACK_FILENAME = "iteration_feedback.json"
APPROVAL_FILENAME = "approval.json"

# marker substring (scanned case-sensitively, matching the ADK original) ->
# (approval.json key, value) it sets when found anywhere in a saved
# feedback payload.
APPROVAL_MARKERS = {
    "COMPLIANCE APPROVED": ("compliance_status", "APPROVED"),
    "SIMULATION_ALL_APPROVED": ("simulation_status", "APPROVED"),
    "GROUNDING APPROVED": ("grounding_status", "APPROVED"),
    "CLOUDARCH APPROVED": ("cloudarch_status", "APPROVED"),
    "JSON APPROVED": ("status", "JSON APPROVED"),
}

APPROVED_STATUSES = {
    "JSON APPROVED",
    "COMPLIANCE APPROVED",
    "SIMULATION_ALL_APPROVED",
    "GROUNDING APPROVED",
    "CLOUDARCH APPROVED",
}

# Every channel any network's instructions actually save/load (see the
# "channel=" HOCON references in registries/*.hocon) -- "" is the
# unchanneled default cloudarch uses. A loop that stops at MAX_ITERATIONS
# right after a reviewer writes fresh feedback (but before the generator's
# next call would have drained it -- the generator is never called again
# once the loop decides to stop) leaves that channel's mailbox undrained.
# reset_approval_state() alone doesn't clear these, so a later, UNRELATED
# request against the same network can load and apply that stale feedback
# the moment its own Design_Agent reads the same channel.
KNOWN_CHANNELS = ("", "analysis", "update", "compliance", "simulation")


def _feedback_filename(channel: str = "") -> str:
    # Channel support: CloudArch has exactly one reviewer, so the single
    # shared mailbox never collides. A pipeline with MULTIPLE reviewers in
    # the same pass (e.g. process's Compliance_Agent + Simulation_Agent)
    # would otherwise have the second reviewer's save overwrite the
    # first's before the generator ever reads it -- the ADK original
    # avoided this by draining each reviewer's feedback immediately via a
    # dedicated refinement-clone agent before the next reviewer ran.
    # Separate channels let one generator read every reviewer's feedback
    # together instead, without needing that per-reviewer clone structure.
    return f"iteration_feedback_{channel}.json" if channel else FEEDBACK_FILENAME


def load_iteration_feedback(reset_data: bool = True, channel: str = "") -> Dict[str, Any]:
    """Reads the mailbox a reviewer step last wrote, then drains it (unless
    reset_data=False) so a later, unrelated read never sees stale content."""
    path = output_path(_feedback_filename(channel))
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            feedback = json.load(f)
    except Exception:
        return {"status": "No feedback found", "data": []}

    if reset_data and isinstance(feedback, dict):
        try:
            drained = dict(feedback)
            drained["data"] = []
            # "NONE" is an explicit sentinel distinct from "nothing new since
            # the mailbox was last drained" vs. a genuine (if terse) real
            # review outcome -- see the ADK original's save for why this
            # matters to a later reader.
            drained["status"] = "NONE"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(drained, f, indent=2)
        except Exception:
            pass

    return feedback


def save_iteration_feedback(feedback_data: Any, channel: str = "") -> str:
    """Normalizes a reviewer's payload, updates the cumulative approval
    state for any approval marker found in it, and writes the mailbox."""
    path = output_path(_feedback_filename(channel))

    processed_data = feedback_data
    if isinstance(feedback_data, str):
        try:
            processed_data = json.loads(feedback_data.replace("'", '"'))
        except Exception:
            processed_data = feedback_data

    inner_status = processed_data.get("status") if isinstance(processed_data, dict) else None

    feedback_str = json.dumps(processed_data) if not isinstance(processed_data, str) else processed_data
    matched = [key for key in APPROVAL_MARKERS if key in feedback_str]

    if matched:
        approval_path = output_path(APPROVAL_FILENAME)
        approval_state = {}
        if os.path.exists(approval_path):
            try:
                with open(approval_path, "r", encoding="utf-8") as f:
                    approval_state = json.load(f)
            except Exception:
                approval_state = {}
        for marker in matched:
            key, value = APPROVAL_MARKERS[marker]
            approval_state[key] = value
        with open(approval_path, "w", encoding="utf-8") as f:
            json.dump(approval_state, f, indent=2)

    status = inner_status if inner_status in APPROVED_STATUSES else "REVISION REQUIRED"

    if isinstance(processed_data, dict):
        if "issues" in processed_data:
            processed_data = processed_data["issues"]
        elif "data" in processed_data:
            processed_data = processed_data["data"]
        else:
            processed_data = {k: v for k, v in processed_data.items() if k != "status"}

    payload = {"status": status, "data": processed_data}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return f"SUCCESS: Feedback persisted to {path}"
    except Exception as e:
        return f"ERROR: Could not save feedback: {e}"


def reset_approval_state() -> None:
    """Clears stale approval/stop-counter state left over from an earlier,
    unrelated pipeline run. Call once before a fresh generate/review loop
    starts (see loop_control.py's reset_iteration_counter sibling)."""
    for filename in (APPROVAL_FILENAME,):
        path = output_path(filename)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def reset_feedback_channels() -> None:
    """Clears every known feedback mailbox (see KNOWN_CHANNELS) left over
    from an earlier, unrelated pipeline run -- same timing as
    reset_approval_state's sibling above (call once, as the very first
    action, at the start of a NEW generate-or-refine request)."""
    for channel in KNOWN_CHANNELS:
        path = output_path(_feedback_filename(channel))
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
