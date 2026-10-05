"""The generate/review loop's stop decision -- the one piece of the ADK
original that WAS framework-specific (tool_context.actions.escalate, which
ends an ADK LoopAgent's iteration immediately) and has no neuro-san
primitive equivalent.

Ported from _build_stop_if_ready (utils_agent.py), with "stop the loop" as
a return value a front-man's own instructions are told to treat as
authoritative, instead of a runtime flag. Checked in the same order, for
the same reason (see the ADK original's comment on why approval is checked
BEFORE max-iterations): a genuine approval on the last allowed iteration
must not be reported as "iteration budget exhausted".

A front-man agent's instructions should say, verbatim in spirit: "call
Generator, then call Reviewer, then call loop_control with the required
approval key(s) for this pipeline and max_iterations; if verdict is
CONTINUE, call Generator again with the reviewer's feedback attached; if
verdict is STOP, do not call Generator or Reviewer again this turn."
"""

import asyncio
import json
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.iteration_feedback import APPROVAL_FILENAME
from coded_tools.common.paths import output_path

STOP_COUNTER_FILENAME = "stop_counter.json"


def _load_count() -> int:
    path = output_path(STOP_COUNTER_FILENAME)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(json.load(f).get("count", 0))
    except Exception:
        return 0


def _save_count(count: int) -> None:
    try:
        with open(output_path(STOP_COUNTER_FILENAME), "w", encoding="utf-8") as f:
            json.dump({"count": count}, f)
    except Exception:
        pass


def reset_iteration_counter() -> None:
    """Call once before a fresh generate/review loop starts (same timing as
    the ADK original's before_agent_callback / per-pipeline analysis-stage
    reset) so a stale counter from an earlier run doesn't short-circuit a
    new one."""
    path = output_path(STOP_COUNTER_FILENAME)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _load_approval_state() -> Dict[str, Any]:
    path = output_path(APPROVAL_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class LoopControlCodedTool(CodedTool):
    """Decides whether a pipeline's generate/review loop should continue or
    stop. Hard-stops via LOOP_HARD_STOP=true env var; otherwise stops on
    either full approval or hitting max_iterations, else says continue."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        required: Dict[str, str] = args.get("required") or {}
        max_iterations = int(args.get("max_iterations", 2))

        loop_count = _load_count() + 1
        _save_count(loop_count)

        if os.getenv("LOOP_HARD_STOP", "").strip().lower() in ("1", "true", "yes", "on"):
            reset_iteration_counter()
            return {"verdict": "STOP", "reason": "HARD_STOP"}

        approval_state = _load_approval_state()

        if str(approval_state.get("status", "")).strip().upper() == "JSON APPROVED":
            reset_iteration_counter()
            return {"verdict": "STOP", "reason": "APPROVED"}

        if any(approval_state.get(k) == "JSON APPROVED" for k in required):
            reset_iteration_counter()
            return {"verdict": "STOP", "reason": "APPROVED"}

        if required and all(approval_state.get(k) == v for k, v in required.items()):
            reset_iteration_counter()
            return {"verdict": "STOP", "reason": "APPROVED"}

        if loop_count >= max_iterations:
            reset_iteration_counter()
            return {"verdict": "STOP", "reason": "MAX_ITERATIONS"}

        return {"verdict": "CONTINUE", "iteration": loop_count, "max_iterations": max_iterations}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
