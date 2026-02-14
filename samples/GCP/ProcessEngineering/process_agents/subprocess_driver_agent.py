# process_agents/subprocess_driver_agent.py

import json
import os
import time
import random
import asyncio

from typing import AsyncGenerator, Dict, Any, List

from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types
from typing_extensions import override
from .utils import getProperty

import logging

logger = logging.getLogger("ProcessArchitect.SubProcessDriverAgent")

# IMPORTANT:
# We now import FACTORY FUNCTIONS instead of singletons.
from .subprocess_generator_agent import build_subprocess_generator_agent
from .subprocess_writer_agent import build_subprocess_writer_agent

# ---------------------------------------------------------
# SUBPROCESS DRIVER AGENT
# ---------------------------------------------------------
class SubprocessDriverAgent(BaseAgent):
    """
    Orchestrates subprocess generation for each top-level process step.
    Loads process_steps directly from output/process_data.json
    instead of relying on ADK session state.

    This version is SAFE to instantiate multiple times because
    it creates fresh LLM agents internally.
    """
    per_step_pipeline: SequentialAgent

    def __init__(self, name: str = "Subprocess_Driver_Agent"):
        # 🔥 Create fresh LLMs for this instance
        generator = build_subprocess_generator_agent()
        writer = build_subprocess_writer_agent()

        pipeline = SequentialAgent(
            name=f"Per_Step_Subprocess_Pipeline_{name}",
            sub_agents=[generator, writer],
        )

        # IMPORTANT: pass per_step_pipeline into super().__init__()
        super().__init__(
            name=name,
            sub_agents=[pipeline],
            per_step_pipeline=pipeline,
        )

        # OPTIONAL: assign again for convenience (safe after super())
        self.per_step_pipeline = pipeline

    # ---------------------------------------------------------
    # Load process steps directly from the final JSON file
    # ---------------------------------------------------------
    def _load_process_steps(self) -> List[Dict[str, Any]]:
        path = "output/process_data.json"

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Expected process_data.json at {path}, but file does not exist."
            )

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        steps = data.get("process_steps", [])
        if not isinstance(steps, list):
            raise ValueError("process_steps must be a list in process_data.json")

        return steps

    # ---------------------------------------------------------
    # Main execution
    # ---------------------------------------------------------
    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        try:
            steps = self._load_process_steps()
        except Exception as e:
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"Subprocess Error: {str(e)}")]
                )
            )
            return

        if not steps:
            logger.debug("No process_steps found; skipping subprocess generation.")
            if False:
                yield
            return

        for step in steps:
            step_name = step.get("step_name", "Unnamed Step")
            logger.debug(f"Generating subprocess for step: {step_name}")

            # Store the current step in shared session state
            ctx.session.state["current_process_step"] = step

            # Rate‑limit padding
            await asyncio.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)

            # ---------------------------------------------------------
            # RUN GENERATOR (sub-agent 0) AND CAPTURE ITS OUTPUT
            # ---------------------------------------------------------
            generator_agent = self.per_step_pipeline.sub_agents[0]
            await asyncio.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)

            flow = None
            async for event in generator_agent.run_async(ctx):
                if event.author == generator_agent.name:
                    if event.content and event.content.parts:
                        raw = event.content.parts[0].text
                        try:
                            flow = json.loads(raw)
                        except Exception:
                            flow = raw

            if not flow:
                logger.error(f"[{self.name}] Generator produced no subprocess flow for step '{step_name}'.")
                continue

            # Store the generated subprocess flow in shared session state
            ctx.session.state["current_subprocess_flow"] = flow

            # ---------------------------------------------------------
            # RUN WRITER (sub-agent 1)
            # ---------------------------------------------------------
            await asyncio.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
            writer_agent = self.per_step_pipeline.sub_agents[1]
            async for _ in writer_agent.run_async(ctx):
                pass

        logger.debug("Subprocess generation completed for all steps.")
        
        if False:
            yield

        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part(text="Completed subprocess generation for all steps.")]
            )
        )


# Default instance for the CREATE pipeline
subprocess_driver_agent = SubprocessDriverAgent()
