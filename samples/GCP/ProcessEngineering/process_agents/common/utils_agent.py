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
from process_toolkit.run_lock import (
    acquire_pipeline_lock,
    release_pipeline_lock,
    start_pipeline_lock_heartbeat,
    stop_pipeline_lock_heartbeat,
    force_clear_pipeline_lock,
)
from .artifact_downloads import (
    cloudarch_diagram_exists,
    copy_artifact_to_destination,
    list_output_documents,
    resolve_artifact_target,
)

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
    acquire_pipeline_lock call in that case.

    Also (re)starts this token's background heartbeat (see
    process_toolkit.run_lock) -- idempotent for the reentrant-reuse case
    above, so the two calls within one turn share a single heartbeat
    rather than each starting their own. The heartbeat, not this
    function's own call sites, is what actually keeps a still-running
    pipeline's lease fresh between here and release_pipeline_lock_for_turn
    -- there is no guarantee either tool call happens again soon enough
    on its own (e.g. during a single long generate/review phase, or a
    pause awaiting the next piece of user input)."""
    if context is None:
        token = acquire_pipeline_lock(label)
        start_pipeline_lock_heartbeat(label, token)
        return token

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
    start_pipeline_lock_heartbeat(label, token)
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
    itself a no-op. Stops that token's heartbeat (if any) before
    releasing the lock itself, so the heartbeat can never fire again
    against a lock this call has already given up."""
    stored = context.state.get(PIPELINE_LOCK_TOKEN_STATE_KEY) if context is not None else None
    token = stored.get("token") if isinstance(stored, dict) else None
    stop_pipeline_lock_heartbeat(token)
    release_pipeline_lock(token)


def release_pipeline_lock_after_run(callback_context=None) -> None:
    """after_agent_callback for each create/update pipeline's own
    top-level SequentialAgent (process/design, create/update -- all
    four) -- releases this turn's pipeline lock once the WHOLE
    pipeline's run ends, for ANY reason, closing a real gap: each
    pipeline's own finalize step (create_standard_doc_from_file, in
    doc_generation_agent.py) only releases the lock when it is actually
    reached AND returns a "SUCCESS:" result. Confirmed directly: a run
    that stops after Stage 1 -- e.g. the agent asks a clarifying
    question in plain text instead of proceeding, with no further tool
    calls that turn -- left the lock held indefinitely, refusing every
    later run against the same output/ directory ("Another pipeline run
    ... is already in progress") until the server process itself
    restarted. The lock's own staleness fallback (process_toolkit.
    run_lock.DEFAULT_STALE_AFTER_SECONDS) can't help here: the
    background heartbeat that same module starts keeps re-acquiring the
    same token every few minutes for as long as this process keeps
    running, so an unreleased lock never actually goes stale on its own
    -- only a process restart ages it out.

    ADK fires after_agent_callback on a SequentialAgent exactly the same
    way it does on CloudArch_Pipeline's own LoopAgent (see
    cloudarch_pipeline_agent.py's before/after pair) -- this is not
    LoopAgent-specific machinery, confirmed directly against ADK's own
    BaseAgent/SequentialAgent source. It fires on normal completion
    (including a plain-text final response with no more tool calls,
    which does not set ctx.end_invocation) -- precisely the case that
    was previously unhandled.

    Safe to call even when the pipeline's own finalize step already
    released this same token moments earlier -- release_pipeline_lock
    only removes the lock file if its token still matches what's
    recorded there (a no-op otherwise), and stop_pipeline_lock_heartbeat
    is a no-op for a token with no running heartbeat -- so this is never
    a SECOND, conflicting release, only a harmless no-op in the already-
    released case and the actual fix in the previously-unreleased one.
    Also safe when this run's own analysis stage never got far enough to
    acquire a lock at all (release_pipeline_lock_for_turn's own
    docstring: context=None or an empty/missing key is itself a no-op).
    """
    release_pipeline_lock_for_turn(callback_context)


def clear_pipeline_lock() -> str:
    """Forcibly clears the shared output/ directory's pipeline lock, if
    one is currently held -- regardless of how old it is or which run
    holds it.

    Call this ONLY when the user explicitly asks to clear, reset, or
    unstick a pipeline lock -- e.g. they saw "Another pipeline run ...
    is already in progress" and are confident nothing is actually still
    running. NEVER call this as your own troubleshooting guess, and
    never in response to a request that is just a normal pipeline run
    (that always goes through the real pipeline tools, not this one).
    Forcibly clearing a lock a genuinely still-running pipeline holds
    can let two runs interleave their writes to the same output/
    directory and corrupt it -- that judgment call belongs to the user,
    since only they know whether another request of theirs is actually
    still in flight elsewhere.
    """
    cleared = force_clear_pipeline_lock()
    if cleared is None:
        return "No pipeline lock is currently held -- there was nothing to clear."

    label = cleared.get("label", "an unknown pipeline")
    started_at = cleared.get("started_at")
    age_str = ""
    if isinstance(started_at, (int, float)):
        age_minutes = (time.time() - started_at) / 60
        age_str = f", held for about {age_minutes:.1f} minute{'s' if abs(age_minutes - 1) > 0.05 else ''}"
    return f"SUCCESS: Cleared the pipeline lock (was held by '{label}'{age_str}). You can retry your request now."


def download_artifact(target: str = "", destination: str = "") -> str:
    """Saves a copy of a generated artifact (the cloud architecture
    diagram, or a generated Word document) to a local filesystem path on
    the machine this agent process is running on.

    Call this when the user explicitly asks to download/save/export/copy
    a generated artifact to a specific location (e.g. "download the cloud
    architecture diagram to /tmp", "save the design doc to my Desktop").
    Do NOT call this just because a document/diagram was generated --
    only on an explicit request to save a copy somewhere.

    IMPORTANT: this writes a file to the filesystem of whatever machine is
    actually running this agent process. On a purely local CLI session
    that's the user's own machine, exactly as if they'd copied the file
    themselves. If this agent is ever served remotely (e.g. via -d) to a
    client that is NOT the same person operating the server, this tool
    would write to the SERVER's own filesystem at a remote user's
    request -- a meaningfully different trust boundary. Do not widen this
    agent's remote exposure without reconsidering this tool's own access
    first.

    Args:
        target: Which artifact to save -- a phrase containing
            "cloudarch"/"diagram"/"architecture" for the cloud
            architecture diagram; an exact generated document filename if
            the user named one; or leave empty to mean whichever document
            was generated most recently (use this for a vague "the
            document"/"it" when context makes it unambiguous).
        destination: The local filesystem path to save it to -- a
            directory (the file keeps its own name) or a full target file
            path. Required.

    Returns:
        A plain-language result: "SUCCESS: ..." naming where the file was
        saved, or "ERROR: ..." naming what's actually available when the
        target couldn't be resolved.
    """
    if not destination:
        return "ERROR: A destination path is required -- ask the user where to save it."

    filename = resolve_artifact_target(target)
    if filename is None:
        available = [doc["filename"] for doc in list_output_documents()]
        if cloudarch_diagram_exists():
            available.insert(0, "the cloud architecture diagram (cloudarch_drawio.xml)")
        listing = ", ".join(available) if available else "nothing has been generated yet"
        target_desc = f"'{target}'" if target else "(no target specified)"
        return f"ERROR: Could not find a generated artifact matching {target_desc}. Available: {listing}."

    try:
        dest_path = copy_artifact_to_destination(filename, destination)
    except (ValueError, OSError) as e:
        return f"ERROR: Could not save '{filename}' to '{destination}': {e}"

    return f"SUCCESS: Saved '{filename}' to {dest_path}."


# context.state key (scoped to the whole chat session, same as
# PIPELINE_LOCK_TOKEN_STATE_KEY above) marking that THIS session has
# already touched the cloud-architecture subsystem at least once. See
# claim_cloudarch_drawio_for_session's own docstring.
CLOUDARCH_DRAWIO_SESSION_OWNED_STATE_KEY = "_cloudarch_drawio_session_owned"


def claim_cloudarch_drawio_for_session(context) -> bool:
    """Returns True only the first time this is called for the current
    chat session, and marks the session as having claimed
    output/cloudarch_drawio.xml from then on (every later call in the
    same session returns False). context may be None (a direct/test
    call with no ADK-managed context) -- always returns False in that
    case, since there is no session to gate on.

    Two different CloudArch-family entry points call this on a session's
    first touch, with different consequences for whatever is currently
    on disk:
      - cloudarch_pipeline_agent._reset_cloudarch_approval_state (the
        generate/refine pipeline's own reset step): if this call returns
        True, any existing diagram could only be a stale leftover from a
        different, unrelated session (this one has never touched it
        before), so the caller deletes it before generation/refinement
        starts.
      - the read-only query agents' own before_agent_callback
        (see claim_cloudarch_drawio_readonly below): if this call
        returns True, the caller does NOT delete anything -- a read-only
        question must never destroy data just because the session
        hasn't looked at it yet; it simply adopts whatever is on disk as
        this session's own.

    Whichever of the two runs first in a given session wins -- this is a
    per-session one-shot regardless of which CloudArch-family agent
    makes the call first."""
    if context is None or context.state.get(CLOUDARCH_DRAWIO_SESSION_OWNED_STATE_KEY):
        return False
    context.state[CLOUDARCH_DRAWIO_SESSION_OWNED_STATE_KEY] = True
    return True


def claim_cloudarch_drawio_readonly(callback_context=None) -> None:
    """before_agent_callback for the read-only CloudArch query agents
    (Consultant/Simulation/Attack-Simulation/FinOps): claims this
    session's ownership of the cloud-architecture diagram the same way
    claim_cloudarch_drawio_for_session does, but only for that side
    effect -- always returns None (never short-circuits the agent),
    since a read-only question must never be blocked or have its
    response substituted just because this happens to be the session's
    first touch."""
    claim_cloudarch_drawio_for_session(callback_context)
    return None

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


def _build_stop_if_ready(required_keys_fn):
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
    """

    def stop_if_ready(tool_context: ToolContext):
        """
        Hard stop if either:
          - loopHardStop property is "true"/"1"/"on"; OR
          - approval.json indicates all required approvals; OR
          - persistent loop counter exceeds SAFE_LOOP_ITERS
        """
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
# reference it this way.
stop_if_ready = _build_stop_if_ready(_default_required_approvals)

# CloudArch's reviewer writes cloudarch_status, not compliance/simulation/
# grounding_status -- see _build_stop_if_ready's docstring. Used by
# cloudarch_pipeline_agent.py's stop-controller clone instead of the
# default stop_if_ready.
cloudarch_stop_if_ready = _build_stop_if_ready(lambda: {"cloudarch_status": "APPROVED"})

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