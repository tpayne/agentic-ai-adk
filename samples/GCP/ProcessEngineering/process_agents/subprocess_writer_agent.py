# process_agents/subprocess_writer_agent.py

import os
import json
import time

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types
from typing import AsyncGenerator
from typing_extensions import override

SUBPROCESS_DIR = "output/subprocesses"
os.makedirs(SUBPROCESS_DIR, exist_ok=True)


class SubprocessWriterAgent(BaseAgent):
    """
    Writes the current_subprocess_flow from session state to a JSON file.
    One file per top-level step, e.g. output/subprocesses/Planning.json
    """

    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        flow = ctx.session.state.get("current_subprocess_flow")
        if not flow:
            msg = "No subprocess flow found in state; nothing to write."
            yield Event(
                author=self.name,
                content=types.Content(role="model", parts=[types.Part(text=msg)]),
            )
            return

        try:
            # flow is likely a Pydantic model; ensure we can serialize
            if hasattr(flow, "model_dump"):
                flow_dict = flow.model_dump()
            else:
                flow_dict = flow

            step_name = flow_dict.get("step_name", "UnknownStep")
            safe_step_name = "".join(
                c if c.isalnum() or c in ("-", "_") else "_" for c in step_name
            )
            filename = f"{safe_step_name}.json"
            path = os.path.join(SUBPROCESS_DIR, filename)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(flow_dict, f, indent=2)

            msg = f"Subprocess flow for '{step_name}' written to {path}."
        except Exception as e:
            msg = f"Failed to write subprocess flow: {e}"

        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=msg)]),
        )


subprocess_writer_agent = SubprocessWriterAgent(name="Subprocess_Writer_Agent")
