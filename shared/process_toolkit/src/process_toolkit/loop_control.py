"""The generate/review loop's stop decision.

ADK's `tool_context.actions.escalate` (which ends an ADK LoopAgent's
iteration immediately) has no neuro-san primitive equivalent, so each
backend needs its own thin adapter around this pure decision -- ADK's
sets `tool_context.actions.escalate`; neuro-san's returns a verdict dict
a front-man's own instructions are told to treat as authoritative. Both
adapters resolve their own config (hard-stop flag, max_iterations) into
plain arguments and call evaluate_loop_stop below; this module has no
opinion on where that config comes from.

Checked in this exact order -- approval BEFORE max-iterations -- because
a genuine approval on the final allowed iteration must report as
approved, not exhausted.
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Literal

from process_toolkit import paths

STOP_COUNTER_FILENAME = "stop_counter.json"
APPROVAL_FILENAME = "approval.json"

Verdict = Literal["STOP", "CONTINUE"]
Reason = Literal["HARD_STOP", "APPROVED", "MAX_ITERATIONS", "CONTINUE"]


@dataclass(frozen=True)
class LoopDecision:
    verdict: Verdict
    reason: Reason
    iteration: int
    max_iterations: int


def evaluate_loop_stop(
    *,
    loop_count: int,
    max_iterations: int,
    hard_stop: bool,
    approval_state: Dict[str, Any],
    required_approvals: Dict[str, str],
) -> LoopDecision:
    if hard_stop:
        return LoopDecision("STOP", "HARD_STOP", loop_count, max_iterations)

    status = str(approval_state.get("status", "")).strip().upper()
    if status == "JSON APPROVED":
        return LoopDecision("STOP", "APPROVED", loop_count, max_iterations)
    if any(approval_state.get(k) == "JSON APPROVED" for k in required_approvals):
        return LoopDecision("STOP", "APPROVED", loop_count, max_iterations)
    if required_approvals and all(approval_state.get(k) == v for k, v in required_approvals.items()):
        return LoopDecision("STOP", "APPROVED", loop_count, max_iterations)

    if loop_count >= max_iterations:
        return LoopDecision("STOP", "MAX_ITERATIONS", loop_count, max_iterations)

    return LoopDecision("CONTINUE", "CONTINUE", loop_count, max_iterations)


def load_counter() -> int:
    path = paths.output_path(STOP_COUNTER_FILENAME)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(json.load(f).get("count", 0))
    except Exception:
        return 0


def save_counter(count: int) -> None:
    try:
        with open(paths.output_path(STOP_COUNTER_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"count": count}, f)
    except Exception:
        pass


def reset_counter() -> None:
    """Call once before a fresh generate/review loop starts, so a stale
    counter from an earlier run doesn't short-circuit a new one."""
    path = paths.output_path(STOP_COUNTER_FILENAME)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def load_approval_state() -> Dict[str, Any]:
    path = paths.output_path(APPROVAL_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
