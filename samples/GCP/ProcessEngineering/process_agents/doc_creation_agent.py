# process_agents/doc_creation_agent.py

from google.adk.agents import SequentialAgent, BaseAgent
from typing import AsyncGenerator
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

# Import ORIGINAL base agent definitions (not cloned copies)
from .edge_inference_agent import edge_inference_agent
from .doc_generation_agent import doc_generation_agent

import logging
logger = logging.getLogger("ProcessArchitect.DocCreationPipeline")


def build_edge_inference_instance():
    """Returns a fresh LlmAgent copy of edge_inference_agent."""
    cls = edge_inference_agent.__class__
    return cls(
        name=edge_inference_agent.name + "_Instance",
        model=edge_inference_agent.model,
        description=edge_inference_agent.description,
        instruction=edge_inference_agent.instruction,
        tools=edge_inference_agent.tools,
        generate_content_config=edge_inference_agent.generate_content_config,
        output_key=edge_inference_agent.output_key,
        before_model_callback=edge_inference_agent.before_model_callback,
        after_model_callback=edge_inference_agent.after_model_callback,
    )


def build_doc_generation_instance():
    """Returns a fresh LlmAgent copy of doc_generation_agent."""
    cls = doc_generation_agent.__class__
    return cls(
        name=doc_generation_agent.name + "_Instance",
        model=doc_generation_agent.model,
        description=doc_generation_agent.description,
        instruction=doc_generation_agent.instruction,
        tools=doc_generation_agent.tools,
        generate_content_config=doc_generation_agent.generate_content_config,
        output_key=doc_generation_agent.output_key,
        before_model_callback=doc_generation_agent.before_model_callback,
        after_model_callback=doc_generation_agent.after_model_callback,
    )


class DocCreationAgent(BaseAgent):
    """
    Reusable 2‑stage pipeline:
        Stage 5: Logical Flow (edge_inference)
        Stage 6: Document Build (doc_generation)
    """

    pipeline: SequentialAgent | None = None  # Prevent ADK attribute validation failures

    def __init__(self, name="Doc_Creation_Agent"):
        # Create fresh instances for each execution
        edge = build_edge_inference_instance()
        doc = build_doc_generation_instance()

        # Wrap them inside a sequential pipeline
        seq = SequentialAgent(
            name=f"{name}_Sequence",
            sub_agents=[edge, doc],
        )

        # Initialize BaseAgent with the sequential agent as its single subnode
        super().__init__(name=name, sub_agents=[seq])

        self.pipeline = seq

    # -----------------------------------------------------------
    # REQUIRED: The ADK runtime calls _run_async_impl, not run().
    # We must forward execution to the inner SequentialAgent.
    # -----------------------------------------------------------
    async def _run_async_impl(
        self,
        ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:

        if not self.pipeline:
            raise RuntimeError("DocCreationAgent pipeline is not initialized.")

        # Stream all events coming from the internal pipeline
        async for event in self.pipeline.run_async(ctx):
            yield event


# -------------------------------------------------------------------------
# Factory function — required for dynamically naming the agent instances
# -------------------------------------------------------------------------
def build_doc_creation_agent(name="Doc_Creation_Agent") -> DocCreationAgent:
    return DocCreationAgent(name=name)


# Optional default instance (keeps consistency with other agents)
doc_creation_agent = DocCreationAgent()