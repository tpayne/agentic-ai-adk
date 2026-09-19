# process_agents/design_doc_update_agent.py

import logging
from google.adk.agents import LoopAgent, SequentialAgent

from .utils import (
    load_full_design_context,
    getProperty,
    save_iteration_feedback,
    load_iteration_feedback,
)

from .design_doc_analysis_agent import log_analysis_metadata
from .design_doc_hld_agent import design_doc_hld_agent
from .design_doc_lld_agent import design_doc_lld_agent
from .design_doc_agent import design_doc_agent
from .design_doc_compliance_agent import design_doc_compliance_agent

from .json_normalizer_agent import json_normalizer_agent
from .json_review_agent import json_review_agent
from .doc_creation_agent import build_doc_creation_agent
from .json_writer_agent import json_writer_agent
from .grounding_agent import grounding_agent

from .utils_agent import (
    mute_agent,
    unmute_agent,
    stop_controller_agent
)
from .agent_wrappers import ProcessLlmAgent, ProcessAgent

logger = logging.getLogger("ProcessArchitect.DesignDocUpdatePipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))

# ---------------------------------------------------------
# UTILITY AGENT CLONES
# ---------------------------------------------------------
mute_agent_instance = ProcessAgent(
    name=mute_agent.name + "_DesignDoc_Update",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_DesignDoc_Update",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_DesignDoc_Update",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
)

# ---------------------------------------------------------
# STAGE 1: CONTEXT-AWARE UPDATE ANALYSIS
# ---------------------------------------------------------
update_design_doc_analysis_agent = ProcessLlmAgent(
    name="Design_Doc_Update_Analyst",
    description="Analyzes user requests for architectural changes and identifies required revisions against the existing design document.",
    instruction_file="design_doc_update_analysis_agent.txt",
    tools=[
        load_full_design_context,
        load_iteration_feedback,
        log_analysis_metadata,
        save_iteration_feedback
    ],
)

# ---------------------------------------------------------
# STAGE 2: PIPELINE AGENT CLONES
# ---------------------------------------------------------
design_doc_hld_update_inst = ProcessLlmAgent(
    name=design_doc_hld_agent.name + "_Update",
    model=design_doc_hld_agent.model,
    description=design_doc_hld_agent.description,
    instruction=design_doc_hld_agent.instruction,
    tools=design_doc_hld_agent.tools,
    generate_content_config=design_doc_hld_agent.generate_content_config,
    output_key=design_doc_hld_agent.output_key,
    before_model_callback=design_doc_hld_agent.before_model_callback,
    after_model_callback=design_doc_hld_agent.after_model_callback
)

design_doc_lld_update_inst = ProcessLlmAgent(
    name=design_doc_lld_agent.name + "_Update",
    model=design_doc_lld_agent.model,
    description=design_doc_lld_agent.description,
    instruction=design_doc_lld_agent.instruction,
    tools=design_doc_lld_agent.tools,
    generate_content_config=design_doc_lld_agent.generate_content_config,
    output_key=design_doc_lld_agent.output_key,
    before_model_callback=design_doc_lld_agent.before_model_callback,
    after_model_callback=design_doc_lld_agent.after_model_callback
)

design_doc_compliance_update_inst = ProcessLlmAgent(
    name=design_doc_compliance_agent.name + "_Update",
    model=design_doc_compliance_agent.model,
    description=design_doc_compliance_agent.description,
    instruction=design_doc_compliance_agent.instruction,
    tools=design_doc_compliance_agent.tools,
    output_key=design_doc_compliance_agent.output_key,
    generate_content_config=design_doc_compliance_agent.generate_content_config,
    before_model_callback=design_doc_compliance_agent.before_model_callback,
    after_model_callback=design_doc_compliance_agent.after_model_callback
)

design_doc_refinement_update_inst = ProcessAgent(
    name=design_doc_agent.name + "_Refinement_Update",
    model=design_doc_agent.model,
    description=design_doc_agent.description,
    instruction=design_doc_agent.instruction,
    tools=design_doc_agent.tools,
    output_key=design_doc_agent.output_key,
    before_model_callback=design_doc_agent.before_model_callback,
    after_model_callback=design_doc_agent.after_model_callback
)

# Grounding pair, mirroring update_process_agent.py's grounding_inst +
# design_grounding_inst: an auditor clone of the shared grounding_agent,
# followed by a refiner clone of design_doc_agent that applies whatever
# the auditor flags -- the same role design_doc_refinement_update_inst
# already plays for HLD/LLD/compliance feedback. Renamed clones, not the
# shared grounding_agent/design_doc_agent objects directly, since
# grounding_agent is already a child agent in the create pipeline's own
# tree (and design_doc_agent is reused multiple times in this same
# pipeline already) -- an ADK agent can only have one parent.
grounding_update_inst = ProcessLlmAgent(
    name=grounding_agent.name + "_DesignDoc_Update",
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
    name=design_doc_agent.name + "_Grounding_Update",
    model=design_doc_agent.model,
    description=design_doc_agent.description,
    instruction=design_doc_agent.instruction,
    tools=design_doc_agent.tools,
    output_key=design_doc_agent.output_key,
    before_model_callback=design_doc_agent.before_model_callback,
    after_model_callback=design_doc_agent.after_model_callback,
)

normalizer_inst = ProcessLlmAgent(
    name=json_normalizer_agent.name + "_DesignDoc_Update",
    model=json_normalizer_agent.model,
    description=json_normalizer_agent.description,
    instruction=json_normalizer_agent.instruction,
    tools=json_normalizer_agent.tools,
    generate_content_config=json_normalizer_agent.generate_content_config,
    output_key=json_normalizer_agent.output_key,
    include_contents=json_normalizer_agent.include_contents,
    before_model_callback=json_normalizer_agent.before_model_callback,
    after_model_callback=json_normalizer_agent.after_model_callback
)

reviewer_inst = ProcessLlmAgent(
    name=json_review_agent.name + "_DesignDoc_Update",
    model=json_review_agent.model,
    description=json_review_agent.description,
    instruction=json_review_agent.instruction,
    tools=json_review_agent.tools,
    generate_content_config=json_review_agent.generate_content_config,
    output_key=json_review_agent.output_key,
    include_contents=json_review_agent.include_contents,
    before_model_callback=json_review_agent.before_model_callback,
    after_model_callback=json_review_agent.after_model_callback
)

writer_inst = ProcessAgent(
    name=json_writer_agent.name + "_DesignDoc_Update",
    model=json_writer_agent.model,
    description=json_writer_agent.description,
    instruction=json_writer_agent.instruction,
    tools=json_writer_agent.tools,
    generate_content_config=json_writer_agent.generate_content_config,
    output_key=json_writer_agent.output_key,
    before_model_callback=json_writer_agent.before_model_callback,
    after_model_callback=json_writer_agent.after_model_callback
)

# ---------------------------------------------------------
# UPDATE REVIEW LOOP
# ---------------------------------------------------------
sub_update_agents = [
    design_doc_hld_update_inst,
    design_doc_lld_update_inst,
    design_doc_compliance_update_inst,
    design_doc_refinement_update_inst,
]

# Optionally include grounding agents, same gate/flag the process
# update pipeline uses (update_process_agent.py).
if getProperty("enableGroundingAgent", default="true"):
    logger.debug("Grounding agent ENABLED in design doc update loop.")
    sub_update_agents += [
        grounding_update_inst,
        design_doc_grounding_instance,
    ]
else:
    logger.debug("Grounding agent DISABLED in design doc update loop.")

sub_update_agents.append(stop_controller_agent_instance)

review_update_loop = LoopAgent(
    name="Design_Doc_Update_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Design_Doc_Update_Stage",
            sub_agents=sub_update_agents,
        )
    ],
    max_iterations=SAFE_LOOP_ITERS,
)

# ---------------------------------------------------------
# JSON NORMALIZATION PIPELINE
# ---------------------------------------------------------
json_stop_agent_instance = ProcessAgent(
    name="JSON_Review_Stop_Controller_DesignDoc_Update",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

json_update_normalization_loop = SequentialAgent(
    name="Design_Doc_Update_Normalization_Loop",
    sub_agents=[
        LoopAgent(
            name="Design_Doc_Update_Normalizer_Sequence",
            sub_agents=[normalizer_inst, reviewer_inst, json_stop_agent_instance],
            max_iterations=SAFE_LOOP_ITERS,
        ),
        writer_inst,
    ],
)

# ---------------------------------------------------------
# UPDATE DESIGN DOC PIPELINE
# ---------------------------------------------------------
update_design_doc_pipeline = SequentialAgent(
    name="Update_Design_Doc_Pipeline",
    description="Use this tool ONLY when the user wants to MODIFY, CHANGE, or UPDATE an existing Architectural Design Document.",
    sub_agents=[
        mute_agent_instance,                 # Mute console output
        update_design_doc_analysis_agent,    # Step 1: Context Loading & Merging
        review_update_loop,                  # Step 2: HLD/LLD Re-Design & Audit Loop
        json_update_normalization_loop,      # Step 3: Stabilization
        build_doc_creation_agent("UpdateDoc"),# Stage 4: Artifact Build
        unmute_agent_instance,               # Unmute console output
    ],
)
