# process_agents/subprocess_writer_agent.py

import os
import json
import logging
from typing import AsyncGenerator
import time
import random
import asyncio

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types
from typing_extensions import override

from ..common.utils import getProperty, safe_filename_component

logger = logging.getLogger("ProcessArchitect.SubProcessWriterAgent")

SUBPROCESS_DIR = "output/subprocesses"
os.makedirs(SUBPROCESS_DIR, exist_ok=True)

class SubprocessWriterAgent(BaseAgent):
    """
    Second half of the per-step pipeline SubprocessDriverAgent builds
    (generator -> writer): takes the SubprocessFlow the generator agent
    just produced (read from ctx.session.state["current_subprocess_flow"],
    not passed directly) and persists it to its own JSON file under
    output/subprocesses/, named after the parent process step.
    """

    def __init__(self, name="Subprocess_Writer_Agent"):
        super().__init__(name=name)

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:

        # ---------------------------------------------------------
        # Retrieve the subprocess flow from shared session state
        # ---------------------------------------------------------
        flow = ctx.session.state.get("current_subprocess_flow")

        if not flow:
            logger.error(
                f"[{self.name}] No subprocess flow found in ctx.session.state"
            )
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="Writer Error: No subprocess flow found.")],
                ),
            )
            return

        # ---------------------------------------------------------
        # Determine output path
        # ---------------------------------------------------------
        step = ctx.session.state.get("current_process_step", {})
        raw_step_name = step.get("step_name", "unnamed_step")

        output_dir = SUBPROCESS_DIR
        os.makedirs(output_dir, exist_ok=True)

        # step_name is LLM-generated content, not a trusted filename. A bare
        # .replace(" ", "_") leaves "/" and ".." untouched, so a step named
        # e.g. "../../../etc/cron.d/evil" or given as an absolute path would
        # let os.path.join escape output_dir entirely (an absolute second
        # argument to os.path.join discards the first outright) and
        # overwrite an arbitrary .json file writable by this process.
        # safe_filename_component collapses it to a single safe path
        # component (strips "/", "..", and other separators); the resolved
        # path is then double-checked to still be inside output_dir before
        # ever being opened for writing.
        step_name = safe_filename_component(raw_step_name)
        output_path = os.path.join(output_dir, f"{step_name}.json")

        resolved_dir = os.path.realpath(output_dir)
        resolved_path = os.path.realpath(output_path)
        if os.path.commonpath([resolved_dir, resolved_path]) != resolved_dir:
            logger.error(
                f"[{self.name}] Refusing to write outside {output_dir}: "
                f"step_name={raw_step_name!r} resolved to {resolved_path!r}"
            )
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="Writer Error: Resolved output path is outside the subprocess output directory.")],
                ),
            )
            return

        await asyncio.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)

        # ---------------------------------------------------------
        # Write the subprocess flow to disk
        # ---------------------------------------------------------
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(flow, f, indent=2)

            logger.debug(
                f"[{self.name}] Wrote subprocess file: {output_path}"
            )

        except Exception as e:
            logger.error(
                f"[{self.name}] Failed to write subprocess file: {e}"
            )
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"Writer Error: {str(e)}")],
                ),
            )
            return

        # ---------------------------------------------------------
        # Writer produces no visible output unless you want it to
        # ---------------------------------------------------------
        if False:
            yield


# -----------------------------
# FACTORY FUNCTION (NEW)
# -----------------------------
def build_subprocess_writer_agent():
    return SubprocessWriterAgent(name="Subprocess_Writer_Agent")


# Keep the original singleton for the CREATE pipeline
subprocess_writer_agent = build_subprocess_writer_agent()
