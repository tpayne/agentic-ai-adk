# process_agents/common/test_specification_pipeline_agent.py
#
# One-shot creation pipeline for the test-specification domain: ensures a
# requirements summary is saved when the request already names a
# directory of source files and none is saved yet (Ensure_Requirements_
# Summary_Agent -- the SAME stage Proposal_Response_Pipeline uses, reused
# here via a fresh clone; see that agent's own module for why a real
# stage is needed rather than a branch inside test_specification_agent.py:
# SequentialAgent stages can't conditionally skip themselves), generates
# test cases validating whichever of the saved requirements/design/cloud
# architecture now exist, saves the specification, then renders it as the
# final document. Deliberately light -- no compliance/simulation review
# loop, no JSON-normalization stage, no subprocess expansion -- mirrors
# Proposal_Response_Pipeline's own shape exactly, including its mute/
# unmute bracketing so this pipeline's own stages produce no intermediate
# chatter, only the final doc-generation stage's own short confirmation.
#
# Unlike Proposal_Response_Pipeline, a requirements summary is NOT
# mandatory here -- a saved design document or cloud architecture diagram
# is just as valid a source -- so the reused Ensure_Requirements_Summary_
# Agent clone below runs under the SAME "optional, never blocks" contract
# documented in its own instructions file; test_specification_agent.py's
# own STEP 1 is what actually decides whether ANY of the three sources
# ended up available.
#
# Reuses build_doc_creation_agent(schema_type="test_specification")
# unchanged for the render stage -- its own edge-inference stage already
# no-ops for "test_specification" (see process_toolkit.docgen.
# edge_inference), so no new rendering code is needed here at all.

from google.adk.agents import SequentialAgent

from .ensure_requirements_summary_agent import ensure_requirements_summary_agent
from .test_specification_agent import test_specification_agent
from .doc_creation_agent import build_doc_creation_agent
from .agent_wrappers import ProcessAgent, ProcessLlmAgent
from .utils_agent import mute_agent, unmute_agent, release_pipeline_lock_after_run

# Fresh clones, not the shared singletons directly -- each ADK BaseAgent
# instance can only have ONE parent, and Proposal_Response_Pipeline
# already claims the mute_agent/unmute_agent/ensure_requirements_summary_
# agent originals as its own children. Every other pipeline in this
# codebase (requirements_doc_pipeline_agent.py, update_process_agent.py,
# design_doc_create_agent.py, design_doc_update_agent.py) follows this
# same clone-not-reuse convention for exactly this reason.
mute_agent_instance = ProcessAgent(
    name=mute_agent.name + "_TestSpecification",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_TestSpecification",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

ensure_requirements_summary_agent_instance = ProcessLlmAgent(
    name=ensure_requirements_summary_agent.name + "_TestSpecification",
    model=ensure_requirements_summary_agent.model,
    description=ensure_requirements_summary_agent.description,
    instruction=ensure_requirements_summary_agent.instruction,
    tools=ensure_requirements_summary_agent.tools,
)

test_specification_pipeline = SequentialAgent(
    name="Test_Specification_Pipeline",
    description=(
        "Use this tool when the user wants test cases generated that VALIDATE whichever of "
        "the saved requirements summary, design document, and cloud architecture diagram "
        "currently exist. Never built from an inline description -- it always reads whichever "
        "of the three are present, and reports if none are found. If no requirements summary "
        "is saved yet AND the request also names a directory of source files to read, this "
        "pipeline analyzes and saves one itself first -- no separate request needed. "
        "Generates test cases (with traceability and a coverage gap analysis) and renders the "
        "final document in one call."
    ),
    sub_agents=[
        mute_agent_instance,
        ensure_requirements_summary_agent_instance,
        test_specification_agent,
        build_doc_creation_agent("Test_Specification_Doc_Creation", schema_type="test_specification"),
        unmute_agent_instance,
    ],
    after_agent_callback=release_pipeline_lock_after_run,
)
