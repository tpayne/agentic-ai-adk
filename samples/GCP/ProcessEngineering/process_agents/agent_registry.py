# Import base/shared agents referenced in pipelines
from .analysis_agent import analysis_agent
from .compliance_agent import compliance_agent
from .consultant_agent import consultant_agent
from .cloudarch_agent import cloudarch_agent
from .create_process_agent import full_design_pipeline
from .doc_creation_agent import build_doc_creation_agent
from .grounding_agent import grounding_agent
from .json_normalizer_agent import json_normalizer_agent
from .json_review_agent import json_review_agent
from .json_writer_agent import json_writer_agent
from .scenario_agent import scenario_tester_agent
from .simulation_agent import simulation_agent
from .simulation_agent import simulation_query_agent
from .subprocess_driver_agent import SubprocessDriverAgent
from .update_process_agent import update_design_pipeline

from .utils_agent import (
    mute_agent, 
    unmute_agent,
    stop_controller_agent
)

# Import the pipeline definitions
from .create_process_agent import (
    design_instance,
    design_compliance_instance,
    design_simulation_instance,
    design_grounding_instance,
    json_stop_agent,
    full_design_pipeline
)

from .update_process_agent import (
    update_analysis_agent,
    design_inst,
    compliance_inst,
    simulation_inst,
    normalizer_inst,
    reviewer_inst,
    design_simulation_inst,
    design_grounding_inst,
    grounding_inst,
    design_compliance_inst,
    json_stop_agent_instance,
    writer_inst,
    mute_agent_instance,
    unmute_agent_instance,
    stop_controller_agent_instance,
    update_design_pipeline
)

# ---------------------------------------------------------------------
# Design Doc (HLD/LLD/Combined) pipelines -- imported with aliases where
# the design-doc modules define instance variables that share a name with
# the process pipeline's own instances above (json_stop_agent,
# mute_agent_instance, unmute_agent_instance, stop_controller_agent_instance,
# normalizer_inst, reviewer_inst, writer_inst, json_stop_agent_instance).
# Importing these unqualified alongside the process pipeline's identically-
# named imports would silently shadow one or the other in this module's
# namespace, corrupting whichever pipeline list is built second. Aliasing
# with a "_dd" suffix keeps both pipelines' instances independently
# addressable.
# ---------------------------------------------------------------------
from .design_doc_analysis_agent import design_doc_analysis_agent
from .design_doc_hld_agent import design_doc_hld_agent
from .design_doc_lld_agent import design_doc_lld_agent
from .design_doc_agent import design_doc_agent
from .design_doc_compliance_agent import design_doc_compliance_agent

from .design_doc_create_agent import (
    design_doc_hld_instance,
    design_doc_lld_instance,
    design_doc_compliance_instance,
    design_doc_refinement_instance,
    json_stop_agent as json_stop_agent_dd,
    full_design_doc_pipeline,
)

from .design_doc_update_agent import (
    update_design_doc_analysis_agent,
    design_doc_hld_update_inst,
    design_doc_lld_update_inst,
    design_doc_compliance_update_inst,
    design_doc_refinement_update_inst,
    normalizer_inst as normalizer_inst_dd,
    reviewer_inst as reviewer_inst_dd,
    writer_inst as writer_inst_dd,
    mute_agent_instance as mute_agent_instance_dd,
    unmute_agent_instance as unmute_agent_instance_dd,
    stop_controller_agent_instance as stop_controller_agent_instance_dd,
    json_stop_agent_instance as json_stop_agent_instance_dd,
    update_design_doc_pipeline,
)

CREATE_PIPELINE_AGENTS = [
    # Stage 1: Analysis
    analysis_agent,
    
    # Stage 2: Design & Review Loop
    design_instance,
    compliance_agent,
    design_compliance_instance,
    simulation_agent,
    design_simulation_instance,
    grounding_agent,
    design_grounding_instance,
    stop_controller_agent,
    
    # Stage 3: Normalization Loop
    json_normalizer_agent,
    json_review_agent,
    json_stop_agent,
    json_writer_agent,
    
    # Utility Agents
    mute_agent,
    unmute_agent
]

UPDATE_PIPELINE_AGENTS = [
    # Stage 1: Context-Aware Analysis
    update_analysis_agent,
    
    # Stage 2: Update & Review Loop
    design_inst,
    compliance_inst,
    design_compliance_inst,
    simulation_inst,
    design_simulation_inst,
    grounding_inst,
    design_grounding_inst,
    
    # Stage 3: Stabilization Loop
    normalizer_inst,
    reviewer_inst,
    json_stop_agent_instance,
    writer_inst,
    
    # Utility Instances
    mute_agent_instance,
    unmute_agent_instance,
    stop_controller_agent_instance
]

CLOUD_AGENTS = [
    cloudarch_agent
]

CREATE_DESIGN_DOC_PIPELINE_AGENTS = [
    # Stage 1: Architectural Requirements Analysis
    design_doc_analysis_agent,

    # Stage 2: HLD/LLD Generation & Governance Audit Loop
    design_doc_hld_instance,
    design_doc_lld_instance,
    design_doc_compliance_instance,
    design_doc_refinement_instance,
    stop_controller_agent,

    # Stage 3: Normalization Loop
    json_normalizer_agent,
    json_review_agent,
    json_stop_agent_dd,
    json_writer_agent,

    # Utility Agents
    mute_agent,
    unmute_agent,
]

UPDATE_DESIGN_DOC_PIPELINE_AGENTS = [
    # Stage 1: Context-Aware Update Analysis
    update_design_doc_analysis_agent,

    # Stage 2: Update & Review Loop
    design_doc_hld_update_inst,
    design_doc_lld_update_inst,
    design_doc_compliance_update_inst,
    design_doc_refinement_update_inst,
    stop_controller_agent_instance_dd,

    # Stage 3: Stabilization Loop
    normalizer_inst_dd,
    reviewer_inst_dd,
    json_stop_agent_instance_dd,
    writer_inst_dd,

    # Utility Instances
    mute_agent_instance_dd,
    unmute_agent_instance_dd,
]
