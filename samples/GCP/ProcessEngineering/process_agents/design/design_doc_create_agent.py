# process_agents/design_doc_create_agent.py

import logging
from google.adk.agents import LoopAgent, SequentialAgent

from .design_doc_analysis_agent import design_doc_analysis_agent
from .design_doc_hld_agent import design_doc_hld_agent
from .design_doc_lld_agent import design_doc_lld_agent
from .design_doc_agent import design_doc_agent
from .design_doc_compliance_agent import design_doc_compliance_agent
from .design_simulation_agent import design_simulation_agent

from ..common.json_normalizer_agent import json_normalizer_agent
from ..common.json_review_agent import json_review_agent
from ..common.json_writer_agent import json_writer_agent
from ..common.doc_creation_agent import build_doc_creation_agent
from ..common.grounding_agent import grounding_agent

from ..common.utils import getProperty
from ..common.utils_agent import (
    mute_agent,
    unmute_agent,
    stop_controller_agent,
)
from ..common.agent_wrappers import ProcessLlmAgent, ProcessAgent

logger = logging.getLogger("ProcessArchitect.DesignDocCreatePipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))

# ---------------------------------------------------------
# AGENT INSTANCES FOR DESIGN DOC CREATION PIPELINE
# ---------------------------------------------------------
design_doc_hld_instance = ProcessLlmAgent(
    name=design_doc_hld_agent.name + "_Create_Instance",
    model=design_doc_hld_agent.model,
    description=design_doc_hld_agent.description,
    instruction=design_doc_hld_agent.instruction,
    tools=design_doc_hld_agent.tools,
    generate_content_config=design_doc_hld_agent.generate_content_config,
    output_key=design_doc_hld_agent.output_key,
    before_model_callback=design_doc_hld_agent.before_model_callback,
    after_model_callback=design_doc_hld_agent.after_model_callback,
)

design_doc_lld_instance = ProcessLlmAgent(
    name=design_doc_lld_agent.name + "_Create_Instance",
    model=design_doc_lld_agent.model,
    description=design_doc_lld_agent.description,
    instruction=design_doc_lld_agent.instruction,
    tools=design_doc_lld_agent.tools,
    generate_content_config=design_doc_lld_agent.generate_content_config,
    output_key=design_doc_lld_agent.output_key,
    before_model_callback=design_doc_lld_agent.before_model_callback,
    after_model_callback=design_doc_lld_agent.after_model_callback,
)

design_doc_compliance_instance = ProcessLlmAgent(
    name=design_doc_compliance_agent.name + "_Create_Instance",
    model=design_doc_compliance_agent.model,
    description=design_doc_compliance_agent.description,
    instruction=design_doc_compliance_agent.instruction,
    tools=design_doc_compliance_agent.tools,
    generate_content_config=design_doc_compliance_agent.generate_content_config,
    output_key=design_doc_compliance_agent.output_key,
    before_model_callback=design_doc_compliance_agent.before_model_callback,
    after_model_callback=design_doc_compliance_agent.after_model_callback,
)

design_doc_refinement_instance = ProcessAgent(
    name=design_doc_agent.name + "_Refinement_Instance",
    model=design_doc_agent.model,
    description=design_doc_agent.description,
    instruction=design_doc_agent.instruction,
    tools=design_doc_agent.tools,
    output_key=design_doc_agent.output_key,
    before_model_callback=design_doc_agent.before_model_callback,
    after_model_callback=design_doc_agent.after_model_callback,
)

# Simulation gate + its own refine-apply clone, mirroring the
# compliance/refinement pair immediately above and the process
# pipeline's simulation_agent + design_simulation_instance in
# create_process_agent.py: design_simulation_agent audits the current
# HLD/LLD against the four-dimension simulation and writes feedback to
# the iteration-feedback mailbox, and this refiner clone of
# design_doc_agent re-reads that mailbox (load_iteration_feedback) and
# applies whatever it flagged, on the next loop iteration.
design_doc_simulation_refinement_instance = ProcessAgent(
    name=design_doc_agent.name + "_Simulation_Refinement_Instance",
    model=design_doc_agent.model,
    description=design_doc_agent.description,
    instruction=design_doc_agent.instruction,
    tools=design_doc_agent.tools,
    output_key=design_doc_agent.output_key,
    before_model_callback=design_doc_agent.before_model_callback,
    after_model_callback=design_doc_agent.after_model_callback,
)

# Grounding pair, mirroring the process pipeline's grounding_agent +
# design_grounding_instance in create_process_agent.py: an auditor clone
# of the shared grounding_agent (validates the design against external
# reality via its OpenAPI tools) followed by a refiner clone of
# design_doc_agent (applies whatever the auditor flags, the same way
# design_doc_refinement_instance applies compliance/HLD/LLD feedback).
# Both are renamed clones rather than the shared grounding_agent/
# design_doc_agent objects reused directly, because grounding_agent is
# already a child agent inside the process pipeline's own tree
# (full_design_pipeline) -- reusing that same instance here would make
# it a child of two different parent agents at once.
grounding_agent_instance = ProcessLlmAgent(
    name=grounding_agent.name + "_DesignDoc_Create",
    model=grounding_agent.model,
    description=grounding_agent.description,
    instruction=grounding_agent.instruction,
    tools=grounding_agent.tools,
    generate_content_config=grounding_agent.generate_content_config,
    output_key=grounding_agent.output_key,
    include_contents=grounding_agent.include_contents,
    before_model_callback=grounding_agent.before_model_callback,
    after_model_callback=grounding_agent.after_model_callback,
)

design_doc_grounding_instance = ProcessAgent(
    name=design_doc_agent.name + "_Grounding_Instance",
    model=design_doc_agent.model,
    description=design_doc_agent.description,
    instruction=design_doc_agent.instruction,
    tools=design_doc_agent.tools,
    output_key=design_doc_agent.output_key,
    before_model_callback=design_doc_agent.before_model_callback,
    after_model_callback=design_doc_agent.after_model_callback,
)

stop_controller_agent_instance = ProcessAgent(
    name="Stop_Controller_DesignDoc_Create",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

mute_agent_instance = ProcessAgent(
    name="Mute_DesignDoc_Create",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
    output_key=mute_agent.output_key,
    before_model_callback=mute_agent.before_model_callback,
    after_model_callback=mute_agent.after_model_callback,
)

unmute_agent_instance = ProcessAgent(
    name="Unmute_DesignDoc_Create",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
    output_key=unmute_agent.output_key,
    before_model_callback=unmute_agent.before_model_callback,
    after_model_callback=unmute_agent.after_model_callback,
)
# ---------------------------------------------------------
# ITERATIVE REVIEW LOOP
# ---------------------------------------------------------
sub_agents = [
    design_doc_hld_instance,
    design_doc_lld_instance,
    design_doc_compliance_instance,
    design_doc_refinement_instance,
    design_simulation_agent,
    design_doc_simulation_refinement_instance,
]

# Optionally include grounding agents, same gate/flag the process
# pipeline uses (create_process_agent.py).
if getProperty("enableGroundingAgent", default="true"):
    logger.debug("Grounding agent ENABLED in design doc loop.")
    sub_agents += [
        grounding_agent_instance,
        design_doc_grounding_instance,
    ]
else:
    logger.debug("Grounding agent DISABLED in design doc loop.")

sub_agents.append(stop_controller_agent_instance)

design_doc_review_loop = LoopAgent(
    name="Design_Doc_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Design_Doc_Stage",
            sub_agents=sub_agents,
        ),
    ],
    max_iterations=SAFE_LOOP_ITERS
)

# ---------------------------------------------------------
# JSON NORMALIZATION PIPELINE
# ---------------------------------------------------------
json_normalizer_agent_instance = ProcessAgent(
    name="JSON_Normalizer_DesignDoc",
    model=json_normalizer_agent.model,
    description=json_normalizer_agent.description,
    instruction=json_normalizer_agent.instruction,
    tools=json_normalizer_agent.tools,
    output_key=json_normalizer_agent.output_key,
    before_model_callback=json_normalizer_agent.before_model_callback,
    after_model_callback=json_normalizer_agent.after_model_callback,
)

json_review_agent_instance = ProcessAgent(
    name="JSON_Review_DesignDoc",
    model=json_review_agent.model,
    description=json_review_agent.description,
    instruction=json_review_agent.instruction,
    tools=json_review_agent.tools,
    output_key=json_review_agent.output_key,
    before_model_callback=json_review_agent.before_model_callback,
    after_model_callback=json_review_agent.after_model_callback,
)

json_stop_agent = ProcessAgent(
    name="JSON_Review_Stop_Controller_DesignDoc",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

json_writer_agent_instance = ProcessAgent(
    name="JSON_Writer_DesignDoc",
    model=json_writer_agent.model,
    description=json_writer_agent.description,
    instruction=json_writer_agent.instruction,
    tools=json_writer_agent.tools,
    output_key=json_writer_agent.output_key,
    before_model_callback=json_writer_agent.before_model_callback,
    after_model_callback=json_writer_agent.after_model_callback,
)

design_doc_json_normalization_loop = SequentialAgent(
    name="Design_Doc_JSON_Normalization_Loop",
    sub_agents=[
        LoopAgent(
            name="Design_Doc_Normalizer_Review_Sequence",
            sub_agents=[json_normalizer_agent_instance, json_review_agent_instance, json_stop_agent],
            max_iterations=SAFE_LOOP_ITERS
        ),
        json_writer_agent_instance
    ],
)

# ---------------------------------------------------------
# FULL DESIGN DOC CREATION PIPELINE
# ---------------------------------------------------------
full_design_doc_pipeline = SequentialAgent(
    name="Full_Design_Doc_Pipeline",
    description="Use this tool ONLY when the user wants to CREATE, DESIGN, or GENERATE a new Architectural Design Document (HLD/LLD) from scratch.",
    sub_agents=[
        mute_agent_instance,                           # Stage 0: Suppress output
        design_doc_analysis_agent,            # Stage 1: Architectural Requirements Analysis
        design_doc_review_loop,               # Stage 2: HLD/LLD Generation & Governance Audit
        design_doc_json_normalization_loop,   # Stage 3: Normalize & Persist Schema JSON
        build_doc_creation_agent("CreateDoc"),# Stage 4: Artifact Document Build
        unmute_agent_instance                          # Stage 5: Restore console output
    ]
)

