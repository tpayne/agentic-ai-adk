# process_agents/doc_creation_agent.py

from typing import AsyncGenerator, Optional

from google.adk.agents import SequentialAgent, BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.tools.tool_context import ToolContext

# Import ORIGINAL base agent definitions (not cloned copies)
from .edge_inference_agent import edge_inference_agent, generate_clean_diagram
from .doc_generation_agent import doc_generation_agent, create_standard_doc_from_file

import logging
logger = logging.getLogger("ProcessArchitect.DocCreationPipeline")

# Deliberately NOT a plain default-value override (e.g. functools.partial)
# for either pinned tool below -- ADK derives a tool's LLM-facing parameter
# schema from the wrapped callable's own signature, and a partial's bound
# keyword argument is still visible there AND can still be overridden by a
# value the LLM supplies for it (confirmed directly:
# functools.partial(fn, schema_type="process")(schema_type="design")
# returns "design", silently winning over the "pinned" value). A real
# wrapper function whose own signature has no schema_type parameter at all
# has nothing for the LLM to see or override.


def _pinned_generate_clean_diagram(schema_type: str):
    def generate_clean_diagram() -> str:
        """Generates the flow/architecture diagram from the current saved baseline. Takes no arguments."""
        return _shared_generate_clean_diagram_pin(schema_type)
    return generate_clean_diagram


def _shared_generate_clean_diagram_pin(schema_type: str) -> str:
    return generate_clean_diagram(schema_type=schema_type)


def _pinned_create_standard_doc_from_file(schema_type: str):
    def create_standard_doc_from_file(
        process_name: str = "Process",
        tool_context: Optional[ToolContext] = None,
    ) -> str:
        """Generates the final Word document from the current saved baseline. process_name is an optional fallback title."""
        return _shared_create_standard_doc_from_file_pin(process_name, schema_type, tool_context)
    return create_standard_doc_from_file


def _shared_create_standard_doc_from_file_pin(
    process_name: str, schema_type: str, tool_context: Optional[ToolContext]
) -> str:
    return create_standard_doc_from_file(process_name, schema_type, tool_context)


def build_edge_inference_instance(schema_type: Optional[str] = None):
    """Returns a fresh LlmAgent copy of edge_inference_agent.

    schema_type: pass "process"/"design" when the calling pipeline's own
    domain is fixed and known (every pipeline except the standalone,
    genuinely domain-agnostic Create_Doc_Agent) -- this replaces the
    LLM-settable generate_clean_diagram tool with a zero-argument version
    hardcoded to that domain, so the model has no opportunity to ground
    the diagram in the wrong document regardless of what else happens to
    exist in output/. Omit it (Create_Doc_Agent's own case) to leave
    schema_type genuinely LLM-controlled, resolved from the user's own
    request wording per this agent's own instruction file."""
    cls = edge_inference_agent.__class__
    tools = [_pinned_generate_clean_diagram(schema_type)] if schema_type is not None else edge_inference_agent.tools
    return cls(
        name=edge_inference_agent.name + "_Instance",
        model=edge_inference_agent.model,
        description=edge_inference_agent.description,
        instruction=edge_inference_agent.instruction,
        tools=tools,
        generate_content_config=edge_inference_agent.generate_content_config,
        output_key=edge_inference_agent.output_key,
        before_model_callback=edge_inference_agent.before_model_callback,
        after_model_callback=edge_inference_agent.after_model_callback,
    )


def build_doc_generation_instance(schema_type: Optional[str] = None):
    """Returns a fresh LlmAgent copy of doc_generation_agent. schema_type:
    see build_edge_inference_instance's own docstring -- identical
    reasoning, applied to create_standard_doc_from_file instead. The
    pinned version keeps process_name as an LLM-settable argument (the
    saved JSON's own title still wins in practice) -- only schema_type is
    removed from what the model can see/set."""
    cls = doc_generation_agent.__class__
    tools = [_pinned_create_standard_doc_from_file(schema_type)] if schema_type is not None else doc_generation_agent.tools
    return cls(
        name=doc_generation_agent.name + "_Instance",
        model=doc_generation_agent.model,
        description=doc_generation_agent.description,
        instruction=doc_generation_agent.instruction,
        tools=tools,
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

    def __init__(self, name="Doc_Creation_Agent", schema_type: Optional[str] = None):
        # schema_type: pass "process"/"design" when this pipeline's own
        # domain is fixed and known -- see build_edge_inference_instance's
        # own docstring. Omit it only for a genuinely domain-agnostic
        # caller (Create_Doc_Agent's own standalone regenerate-document
        # entry point).
        # Create fresh instances for each execution
        edge = build_edge_inference_instance(schema_type)
        doc = build_doc_generation_instance(schema_type)

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
def build_doc_creation_agent(name="Doc_Creation_Agent", schema_type: Optional[str] = None) -> DocCreationAgent:
    return DocCreationAgent(name=name, schema_type=schema_type)


# Optional default instance (keeps consistency with other agents)
doc_creation_agent = DocCreationAgent()