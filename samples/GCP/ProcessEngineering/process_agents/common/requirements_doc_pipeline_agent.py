# process_agents/requirements_doc_pipeline_agent.py
#
# One-shot creation pipeline for the requirements domain: synthesizes a
# requirements register directly from the user's own description (no
# directory of files required -- see requirements_synthesis_agent.py),
# saves it, then renders it as the ISO/IEC/IEEE 29148-style requirements
# document. Deliberately light -- no compliance/simulation review loop,
# no JSON-normalization stage, no subprocess expansion -- unlike
# Full_Design_Pipeline/Full_Design_Doc_Pipeline, which all cover a much
# larger domain. Mirrors Full_Design_Pipeline's own mute/unmute bracketing
# so this pipeline's own two stages produce no intermediate chatter,
# only the final doc-generation stage's own short confirmation.
#
# Reuses build_doc_creation_agent(schema_type="requirements") unchanged
# for the render stage -- its own edge-inference stage already no-ops
# for "requirements" (see process_toolkit.docgen.edge_inference), so no
# new rendering code is needed here at all.

from google.adk.agents import SequentialAgent

from .requirements_synthesis_agent import requirements_synthesis_agent
from .doc_creation_agent import build_doc_creation_agent
from .agent_wrappers import ProcessAgent
from .utils_agent import mute_agent, unmute_agent, release_pipeline_lock_after_run

# Fresh clones, not the shared mute_agent/unmute_agent singletons directly
# -- each ADK BaseAgent instance can only have ONE parent, and
# Full_Design_Pipeline already claims the originals as its own children.
# Every other pipeline in this codebase (update_process_agent.py,
# design_doc_create_agent.py, design_doc_update_agent.py) follows this
# same clone-not-reuse convention for exactly this reason.
mute_agent_instance = ProcessAgent(
    name=mute_agent.name + "_RequirementsDoc",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_RequirementsDoc",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

requirements_doc_pipeline = SequentialAgent(
    name="Requirements_Doc_Pipeline",
    description=(
        "Use this tool ONLY when the user wants to CREATE a new requirements document from a "
        "description of a product/system/initiative (not from an existing directory of files, "
        "and not from an already-saved requirements summary). Synthesizes a requirements "
        "register grounded in the description plus relevant domain/regulatory standards, saves "
        "it, and renders the final ISO/IEC/IEEE 29148-style Word document in one call."
    ),
    sub_agents=[
        mute_agent_instance,
        requirements_synthesis_agent,
        build_doc_creation_agent("Requirements_Doc_Creation", schema_type="requirements"),
        unmute_agent_instance,
    ],
    after_agent_callback=release_pipeline_lock_after_run,
)
