# process_agents/proposal_response_pipeline_agent.py
#
# One-shot creation pipeline for the proposal-response domain: drafts a
# response against an ALREADY-saved requirements summary (no fresh
# requirements analysis here -- that is Requirements_Summary_Agent's own
# separate, prior step -- see proposal_response_agent.py), saves it,
# then renders it as the final Response to Proposal document.
# Deliberately light -- no compliance/simulation review loop, no
# JSON-normalization stage, no subprocess expansion -- mirrors
# Requirements_Doc_Pipeline's own shape exactly, including its mute/
# unmute bracketing so this pipeline's own two stages produce no
# intermediate chatter, only the final doc-generation stage's own short
# confirmation.
#
# Reuses build_doc_creation_agent(schema_type="proposal_response")
# unchanged for the render stage -- its own edge-inference stage already
# no-ops for "proposal_response" (see process_toolkit.docgen.edge_inference),
# so no new rendering code is needed here at all.

from google.adk.agents import SequentialAgent

from .proposal_response_agent import proposal_response_agent
from .doc_creation_agent import build_doc_creation_agent
from .agent_wrappers import ProcessAgent
from .utils_agent import mute_agent, unmute_agent, release_pipeline_lock_after_run

# Fresh clones, not the shared mute_agent/unmute_agent singletons directly
# -- each ADK BaseAgent instance can only have ONE parent, and
# Full_Design_Pipeline already claims the originals as its own children.
# Mirrors requirements_doc_pipeline_agent.py's own identical fix for the
# identical mistake (an ADK single-parent ValidationError, caught during
# that pipeline's own full-suite verification).
mute_agent_instance = ProcessAgent(
    name=mute_agent.name + "_ProposalResponse",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_ProposalResponse",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

proposal_response_pipeline = SequentialAgent(
    name="Proposal_Response_Pipeline",
    description=(
        "Use this tool ONLY when the user wants to CREATE a Response to Proposal document "
        "against an already-saved requirements summary (an RFP/proposal's own analyzed "
        "requirements register) plus a description of the responding organization's "
        "solution/offering. Requires a requirements summary to already be saved -- if none "
        "exists, run a requirements summarization request against the RFP/proposal's own files "
        "first. Drafts the response (including a point-by-point compliance matrix) and renders "
        "the final Word document in one call."
    ),
    sub_agents=[
        mute_agent_instance,
        proposal_response_agent,
        build_doc_creation_agent("Proposal_Response_Doc_Creation", schema_type="proposal_response"),
        unmute_agent_instance,
    ],
    after_agent_callback=release_pipeline_lock_after_run,
)
