"""The generate/review loop's stop decision -- the one piece of the ADK
original that WAS framework-specific (tool_context.actions.escalate, which
ends an ADK LoopAgent's iteration immediately) and has no neuro-san
primitive equivalent. The pure decision logic lives in
process_toolkit.loop_control (shared with the ADK port); this is just the
neuro-san CodedTool adapter around it.

A front-man agent's instructions should say, verbatim in spirit: "call
Generator, then call Reviewer, then call loop_control with the required
approval key(s) for this pipeline and max_iterations; if verdict is
CONTINUE, call Generator again with the reviewer's feedback attached; if
verdict is STOP, do not call Generator or Reviewer again this turn."
"""

import asyncio
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.loop_control import (
    evaluate_loop_stop,
    load_counter,
    save_counter,
    reset_counter as reset_iteration_counter,
    load_approval_state,
)


class LoopControlCodedTool(CodedTool):
    """Decides whether a pipeline's generate/review loop should continue or
    stop. Hard-stops via LOOP_HARD_STOP=true env var; otherwise stops on
    either full approval or hitting max_iterations, else says continue."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        required: Dict[str, str] = args.get("required") or {}
        max_iterations = int(args.get("max_iterations", 2))

        loop_count = load_counter() + 1
        save_counter(loop_count)

        hard_stop = os.getenv("LOOP_HARD_STOP", "").strip().lower() in ("1", "true", "yes", "on")
        decision = evaluate_loop_stop(
            loop_count=loop_count,
            max_iterations=max_iterations,
            hard_stop=hard_stop,
            approval_state=load_approval_state(),
            required_approvals=required,
        )

        if decision.verdict == "STOP":
            reset_iteration_counter()
            return {"verdict": "STOP", "reason": decision.reason}

        return {"verdict": "CONTINUE", "iteration": decision.iteration, "max_iterations": decision.max_iterations}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
