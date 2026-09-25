# process_agents/cloudarch_pipeline_agent.py

import logging
from google.adk.agents import LoopAgent

from ..common.utils import getProperty
from .cloudarch_agent import cloudarch_agent
from .cloudarch_reviewer_agent import cloudarch_reviewer_agent
from ..common.utils_agent import stop_controller_agent
from ..common.agent_wrappers import ProcessAgent

logger = logging.getLogger("ProcessArchitect.CloudArchPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))

# ---------------------------------------------------------
# STOP CONTROLLER CLONE
# ---------------------------------------------------------
# stop_controller_agent is already used bare (unrenamed) as a child agent
# inside create_process_agent.py's review_loop -- an ADK agent can only
# have one parent, so this second consumer clones it, same as
# design_doc_create_agent.py / design_doc_update_agent.py /
# update_process_agent.py all do for the same reason.
stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_CloudArch",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

# ---------------------------------------------------------
# CLOUDARCH GENERATE/REVIEW LOOP
# ---------------------------------------------------------
# Same three-role shape as the JSON normalization loops elsewhere
# (normalizer, reviewer, stop -- see json_normalization_loop in
# create_process_agent.py): cloudarch_agent generates/refines the
# architecture, cloudarch_reviewer_agent audits it and writes feedback
# to the iteration-feedback mailbox, and the stop controller ends the
# loop once the reviewer reports "CLOUDARCH APPROVED". On the next
# iteration cloudarch_agent reads that mailbox (load_iteration_feedback)
# and applies the reviewer's feedback before generating again.
#
# cloudarch_agent and cloudarch_reviewer_agent are used here bare
# (unrenamed) since this is their only pipeline -- neither is a child
# agent anywhere else yet, so no clone is needed for either of them.
cloudarch_review_loop = LoopAgent(
    name="CloudArch_Pipeline",
    description="Use this tool to generate or refine a cloud architecture (drawio diagram), audited by a reviewer agent before it is finalized.",
    sub_agents=[
        cloudarch_agent,
        cloudarch_reviewer_agent,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
)

# ---------------------------------------------------------
# CLOUDARCH PIPELINE
# ---------------------------------------------------------
cloudarch_pipeline = cloudarch_review_loop
