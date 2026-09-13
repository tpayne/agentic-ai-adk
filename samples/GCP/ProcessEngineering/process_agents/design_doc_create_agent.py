# process_agents/design_doc_create_agent.py

import logging
from google.adk.agents import LoopAgent, SequentialAgent

from .design_doc_analysis_agent import design_doc_analysis_agent
from .design_doc_hld_agent import design_doc_hld_agent
from .design_doc_lld_agent import design_doc_lld_agent
from .design_doc_agent import design_doc_agent
from .design_doc_compliance_agent import design_doc_compliance_agent

from .json_normalizer_agent import json_normalizer_agent
from .json_review_agent import json_review_agent
from .json_writer_agent import json_writer_agent
from .doc_creation_agent import build_doc_creation_agent

from .utils import getProperty
from .utils_agent import (
    mute_agent,
    unmute_agent,
    stop_controller_agent
)
from .agent_wrappers import ProcessLlmAgent, ProcessAgent

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

# ---------------------------------------------------------
# ITERATIVE REVIEW LOOP
# ---------------------------------------------------------
sub_agents = [
    design_doc_hld_instance,
    design_doc_lld_instance,
    design_doc_compliance_instance,
    design_doc_refinement_instance,
    stop_controller_agent
]

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

design_doc_json_normalization_loop = SequentialAgent(
    name="Design_Doc_JSON_Normalization_Loop",
    sub_agents=[
        LoopAgent(
            name="Design_Doc_Normalizer_Review_Sequence",
            sub_agents=[json_normalizer_agent, json_review_agent, json_stop_agent],
            max_iterations=SAFE_LOOP_ITERS
        ),
        json_writer_agent
    ],
)

# ---------------------------------------------------------
# FULL DESIGN DOC CREATION PIPELINE
# ---------------------------------------------------------
full_design_doc_pipeline = SequentialAgent(
    name="Full_Design_Doc_Pipeline",
    description="Use this tool ONLY when the user wants to CREATE, DESIGN, or GENERATE a new Architectural Design Document (HLD/LLD) from scratch.",
    sub_agents=[
        mute_agent,                           # Stage 0: Suppress output
        design_doc_analysis_agent,            # Stage 1: Architectural Requirements Analysis
        design_doc_review_loop,               # Stage 2: HLD/LLD Generation & Governance Audit
        design_doc_json_normalization_loop,   # Stage 3: Normalize & Persist Schema JSON
        build_doc_creation_agent("CreateDoc"),# Stage 4: Artifact Document Build
        unmute_agent                          # Stage 5: Restore console output
    ]
)

