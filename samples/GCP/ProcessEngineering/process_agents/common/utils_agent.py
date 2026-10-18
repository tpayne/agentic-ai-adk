# utils_agent.py
import logging
from google.adk.tools.tool_context import ToolContext
import os
import time
import random
import json
import sys

from typing import Any

logger = logging.getLogger("ProcessArchitect.UtilsAgent")

from .utils import (
    getProperty,
    CleanedStdout
)

from process_toolkit.loop_control import (
    evaluate_loop_stop,
    load_counter,
    save_counter,
    reset_counter,
    load_approval_state,
)
from process_toolkit.run_lock import acquire_pipeline_lock, release_pipeline_lock, PipelineLockedError

from ..process.design_agent import design_agent
from .agent_wrappers import ProcessAgent

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# tool_context.state / callback_context.state key for threading a
# process_toolkit.run_lock token between a pipeline's own reset step
# (which acquires the lock) and its own finalize step (which releases
# it) -- separate ADK tool/callback functions, but both operate on the
# SAME session's state within one run. Mirrors the neuro-san port's own
# coded_tools/common/pipeline_lock.py::PIPELINE_LOCK_TOKEN_KEY convention
# (same purpose, different underlying storage mechanism).
#
# Stores {"invocation_id": ..., "token": ...}, not a bare token -- see
# acquire_pipeline_lock_for_turn's own docstring for why the invocation_id
# matters: tool_context.state is scoped to the whole chat SESSION, not to
# one request, so a bare stashed token would be silently reused by a
# SECOND, genuinely different request arriving in that same session while
# the first one is still running, waving it through as "the same run".
PIPELINE_LOCK_TOKEN_STATE_KEY = "_pipeline_lock_token"


def acquire_pipeline_lock_for_turn(label: str, context) -> str:
    """acquire_pipeline_lock, but reentrancy-safe across the TWO separate
    tool calls a create/update pipeline's own analysis stage makes
    moments apart in the same turn (record_analysis_request then
    log_analysis_metadata) -- without also accidentally letting a LATER,
    different turn in the same long-lived chat session inherit an
    earlier turn's still-valid token from state and skip the real
    conflict check entirely. `context` is a ToolContext (the process/
    design-doc analysis agents' own tool functions) or a CallbackContext
    (cloudarch_pipeline_agent.py's before_agent_callback) -- both expose
    the same .invocation_id/.state this function actually uses.

    Gates reuse on context.invocation_id -- an ADK-minted id fresh for
    every top-level run_async() call (one per user turn), distinct from
    the session id, which persists across many turns. The stored token
    is only treated as "mine to refresh" when the invocation_id stored
    alongside it still matches the CURRENT one; a match means this is
    genuinely the second of the two calls within the SAME turn. Anything
    else (nothing stored yet, or a stored invocation_id from an earlier,
    already-superseded turn) mints a fresh token instead, which then
    correctly conflicts against the real lock file if some OTHER turn
    (same session or not) is still actually holding it.

    context may be None (a caller invoked directly, e.g. a test, with no
    ADK-managed context) -- falls back to a plain, non-reentrant
    acquire_pipeline_lock call in that case."""
    if context is None:
        return acquire_pipeline_lock(label)

    current_invocation_id = context.invocation_id
    stored = context.state.get(PIPELINE_LOCK_TOKEN_STATE_KEY)
    reusable_token = None
    if isinstance(stored, dict) and stored.get("invocation_id") == current_invocation_id:
        reusable_token = stored.get("token")

    token = acquire_pipeline_lock(label, token=reusable_token)
    context.state[PIPELINE_LOCK_TOKEN_STATE_KEY] = {
        "invocation_id": current_invocation_id,
        "token": token,
    }
    return token


def release_pipeline_lock_for_turn(context) -> None:
    """Releases whatever token acquire_pipeline_lock_for_turn (or
    cloudarch_pipeline_agent.py's own single-acquire equivalent) stashed
    under PIPELINE_LOCK_TOKEN_STATE_KEY on tool_context/callback_context
    -- a plain `context.state.get(...)` read, not gated on invocation_id
    the way acquire is: by the time a pipeline's own finalize step runs,
    it's always within the SAME turn that acquired the lock in the first
    place, so no cross-turn confusion is possible on the release side.
    Safe to call with context=None or an empty/missing key -- that just
    means nothing was ever acquired, and release_pipeline_lock(None) is
    itself a no-op."""
    stored = context.state.get(PIPELINE_LOCK_TOKEN_STATE_KEY) if context is not None else None
    token = stored.get("token") if isinstance(stored, dict) else None
    release_pipeline_lock(token)

# ---------- Programmatic stop/kill-switch tool ----------
def _contains_marker(obj: Any, needle: str) -> bool:
    """Recursive search for case-insensitive needle in dict/list/str."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    if obj is None:
        return False
    if isinstance(obj, str):
        return needle.lower() in obj.lower()
    if isinstance(obj, dict):
        return any(_contains_marker(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_marker(x, needle) for x in obj)
    return False

def status_logger(goal_count: int):
    """Internal tool to track progress."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"StopAgent - Logger Goals Identified: {goal_count}.")
    return f"Logging status with {goal_count} identified objectives."

def _default_required_approvals() -> dict:
    """Approval-key gate for the process/design-doc pipelines: compliance +
    simulation (+ grounding, if enabled). Evaluated fresh on every call since
    enableGroundingAgent is a static-but-checked-live property."""
    required = {
        "compliance_status": "APPROVED",
        "simulation_status": "APPROVED",
    }
    if getProperty("enableGroundingAgent", default="false"):
        required["grounding_status"] = "APPROVED"
    return required


_STOP_MESSAGES = {
    "HARD_STOP": "Hard stop condition met via loopHardStop property — exiting loop.",
    "APPROVED": "All approvals present — exiting loop.",
    "MAX_ITERATIONS": "Max loop iterations exceeded — exiting loop.",
}


def _build_stop_if_ready(required_keys_fn, lock_refresh_label: str):
    """
    Builds a stop_if_ready tool gated on whatever {approval.json key:
    expected value} mapping `required_keys_fn()` returns.

    This exists because different pipelines write different approval.json
    keys (see save_iteration_feedback's approval_markers in utils.py):
    process/design-doc reviewers write compliance_status/simulation_status/
    grounding_status, but the CloudArch reviewer writes cloudarch_status.
    A single stop_if_ready hardcoded to the first set can never see the
    second -- it would keep reporting "no stop conditions met" and the loop
    would always burn the full loopIterations regardless of whether the
    CloudArch reviewer approved on iteration 1. Each pipeline's stop
    controller must be built with the key set that pipeline's reviewer(s)
    actually write.

    The decision itself (evaluate_loop_stop, shared with the neuro-san
    port) is pure -- this wrapper just resolves ADK's own config sources
    (properties) into plain arguments, calls it, then does the one thing
    only ADK has: setting tool_context.actions.escalate.

    :param lock_refresh_label: Passed to acquire_pipeline_lock_for_turn
            below on every call, purely as a refresh -- see stop_if_ready's
            own comment for why. This tool is called once per loop
            iteration by every pipeline that uses it (process create/update
            and design-doc create/update all clone the SAME stop_if_ready
            instance built with this label; only CloudArch builds its own
            with a distinct one), so a review loop that runs long enough to
            cross DEFAULT_STALE_AFTER_SECONDS between the pipeline's
            one-time reset step and its own finalize step never actually
            goes stale. The refresh reuses whatever token this invocation
            already holds (acquire_pipeline_lock_for_turn's own reentrancy
            check, keyed on tool_context.invocation_id) rather than minting
            anything new, so a label here that doesn't exactly match
            whichever of the four flows is actually running only affects
            the lock file's own diagnostic "label" field (shown to a
            DIFFERENT, genuinely conflicting run's error message) -- never
            which lock gets refreshed or whether it's genuinely this run's.
    """

    def stop_if_ready(tool_context: ToolContext):
        """
        Hard stop if either:
          - loopHardStop property is "true"/"1"/"on"; OR
          - approval.json indicates all required approvals; OR
          - persistent loop counter exceeds SAFE_LOOP_ITERS
        """
        try:
            acquire_pipeline_lock_for_turn(lock_refresh_label, tool_context)
        except PipelineLockedError:
            # Reached only if this invocation never actually held the lock
            # to begin with (defensive -- every pipeline's own reset step
            # acquires it before stop_if_ready can ever run). Refreshing is
            # a courtesy, not stop_if_ready's actual job, so a failure here
            # must not abort the loop-continuation decision below.
            logger.warning("Could not refresh the pipeline lock lease during stop_if_ready.")

        logger.debug("Evaluating stop_if_ready conditions.")

        max_iterations = int(getProperty("loopIterations", default=2))
        hard_stop = str(getProperty("loopHardStop", default=False)).lower() in ("1", "true", "yes", "on")

        loop_count = load_counter() + 1
        save_counter(loop_count)
        logger.debug(f"Stop Controller loop count = {loop_count} / {max_iterations}")

        # Approval-state stop is checked BEFORE the max-iteration stop: the
        # reviewer's own turn (which writes approval.json) always runs
        # immediately before this tool call within the same iteration, so
        # on the last allowed iteration a genuine approval and "iteration
        # budget exhausted" can both be true at once. Checking max-iteration
        # first would report the run as exhausted/incomplete even though it
        # actually succeeded on its last attempt -- confirmed from a real
        # run where the reviewer approved on iteration 2/2, but because the
        # max-iteration check ran first, the stop controller's own visible
        # response described the run as having hit its iteration limit
        # instead of recognizing the approval.
        decision = evaluate_loop_stop(
            loop_count=loop_count,
            max_iterations=max_iterations,
            hard_stop=hard_stop,
            approval_state=load_approval_state(),
            required_approvals=required_keys_fn(),
        )
        logger.debug(f"stop_if_ready decision: {decision}")

        if decision.verdict == "STOP":
            tool_context.actions.escalate = True
            reset_counter()
            return _STOP_MESSAGES[decision.reason]

        return "Continue with loop — no stop conditions met."

    return stop_if_ready


# Default gate: process/design-doc pipelines (compliance + simulation +
# optional grounding). Kept as a module-level `stop_if_ready` name since
# stop_controller_agent below (and its process/design-doc clones) already
# reference it this way. Genuinely shared across four flows (process
# create/update, design-doc create/update), each of which acquired its own
# lock with its own distinct label -- "an active ADK pipeline" is a
# deliberately generic lock_refresh_label rather than any one of theirs;
# see _build_stop_if_ready's own docstring for why that's fine.
stop_if_ready = _build_stop_if_ready(_default_required_approvals, "an active ADK pipeline")

# CloudArch's reviewer writes cloudarch_status, not compliance/simulation/
# grounding_status -- see _build_stop_if_ready's docstring. Used by
# cloudarch_pipeline_agent.py's stop-controller clone instead of the
# default stop_if_ready. Label matches cloudarch_pipeline_agent.py's own
# acquire_pipeline_lock_for_turn call exactly, since this one is never
# shared with another flow.
cloudarch_stop_if_ready = _build_stop_if_ready(lambda: {"cloudarch_status": "APPROVED"}, "the cloud architecture pipeline")

def _reset_stop_counter(counter_path: str):
    """Reset the persistent stop counter."""
    try:
        if os.path.exists(counter_path):
            os.remove(counter_path)
            logger.debug("Stop counter reset.")
    except Exception:
        pass

# ---------- Minimal controller agent that ALWAYS calls the stop tool ----------
stop_controller_agent = ProcessAgent(
    name="Stop_Controller",
    description="Exits the loop immediately when approvals are complete or kill-switch is set.",
    instruction_file="common/stop_controller_agent.txt",
    tools=[status_logger,stop_if_ready],
)

# ---------- Mute agent to consume injected context silently ----------
log_dir = "output/logs"
os.makedirs(log_dir, exist_ok=True)

from .utils import (
    ANSI_GREEN, 
    ANSI_RESET 
)

# Function to kill all console output

def silence_console():
    """
    Redirects sys.stdout to a CleanedStdout-wrapped log file
    (output/logs/runtime_outputs.log) for the duration of a generation
    pipeline run, so verbose ADK/model console chatter doesn't spam the
    user's terminal -- only the one-line "Starting..." banner below is
    printed before the switch. Paired with restore_console, which points
    sys.stdout back at the real terminal once the pipeline finishes.
    """
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug("Silencing console output.")
    print(f"{ANSI_GREEN}- Starting generation pipeline at {time.strftime('%Y-%m-%d %H:%M:%S')}. This will take some time...{ANSI_RESET}", end="\n")
    sys.stdout.flush()
    output_file = os.path.join(log_dir, "runtime_outputs.log")
    sys.stdout = CleanedStdout(output_file)
    return "Console output silenced."

def restore_console():
    """Points sys.stdout back at the real terminal (sys.__stdout__),
    undoing silence_console's redirect once the pipeline run finishes."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug("Restoring console output.")
    previous = sys.stdout
    sys.stdout = sys.__stdout__
    if isinstance(previous, CleanedStdout):
        # silence_console's own file handle -- never closed otherwise, so
        # every silence/restore cycle (one per generation pipeline run)
        # leaked a file descriptor relying on garbage collection to
        # eventually reclaim it instead of a deterministic close.
        previous.close()
    print(f"{ANSI_GREEN}- Finished generation pipeline at {time.strftime('%Y-%m-%d %H:%M:%S')}...{ANSI_RESET}", end="\n")
    sys.stdout.flush()
    return "Console output restored."

mute_agent = ProcessAgent(
    name="Mute_Agent",
    description="Consumes injected context silently.",
    instruction="You MUST just call silence_console as your only action. You MUST NOT produce any output.",
    tools=[silence_console],
)

unmute_agent = ProcessAgent(
    name="Unmute_Agent",
    description="Restores console output.",
    instruction="You MUST just call restore_console as your only action. You MUST NOT produce any output.",
    tools=[restore_console],
)