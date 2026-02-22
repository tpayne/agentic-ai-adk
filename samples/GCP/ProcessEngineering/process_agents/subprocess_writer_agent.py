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

from .utils import getProperty

logger = logging.getLogger("ProcessArchitect.SubProcessWriterAgent")

SUBPROCESS_DIR = "output/subprocesses"
os.makedirs(SUBPROCESS_DIR, exist_ok=True)

class SubprocessWriterAgent(BaseAgent):
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
        step_name = step.get("step_name", "unnamed_step").replace(" ", "_")

        output_dir = SUBPROCESS_DIR
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, f"{step_name}.json")
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
