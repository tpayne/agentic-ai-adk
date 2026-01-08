# process_agents/subprocess_driver_agent.py

import json
import os
import time
import random

from typing import AsyncGenerator, Dict, Any, List

from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types
from typing_extensions import override

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

        # Build the per-step pipeline with fresh agents
        # Added 'f' prefix to make it an f-string
        per_step_pipeline = SequentialAgent(
            name=f"Per_Step_Subprocess_Pipeline_{name}", 
            sub_agents=[generator, writer],
        )

        super().__init__(
            name=name,
            sub_agents=[per_step_pipeline],
            per_step_pipeline=per_step_pipeline,
        )

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
    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:

        try:
            steps = self._load_process_steps()
        except Exception as e:
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"Failed to load process steps: {str(e)}")]
                ),
            )
            return

        if not steps:
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="No process_steps found in process_data.json; skipping subprocess generation.")]
                ),
            )
            return

        # Iterate through each step and run the per-step pipeline
        for step in steps:
            step_name = step.get("step_name", "Unnamed Step")

            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"Generating subprocess for step: {step_name}")]
                ),
            )

            # Push the current step into session state for downstream agents
            ctx.session.state["current_process_step"] = step

            # 🔥 Rate limit protection for subprocess generation
            time.sleep(1.25 + random.random() * 0.75)

            async for event in self.per_step_pipeline.run_async(ctx):
                yield event

        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part(text="Subprocess generation completed for all steps.")]
            ),
        )


# Default instance for the CREATE pipeline
subprocess_driver_agent = SubprocessDriverAgent()
