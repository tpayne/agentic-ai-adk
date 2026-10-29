# process_agents/requirements_synthesis_agent.py
#
# CREATION counterpart to requirements_summary_agent.py: synthesizes a
# brand-new requirements register directly from the user's own
# description of a product/system/initiative (plus general
# domain/regulatory knowledge), rather than reading files. This is
# Requirements_Doc_Pipeline's own first stage -- its own save feeds
# directly into the pipeline's second stage (doc rendering), so this
# agent's visible output stays silent (see its own instruction file's
# OUTPUT CONTRACT), same as process/analysis_agent.py within
# Full_Design_Pipeline.

import logging

logger = logging.getLogger("ProcessArchitect.RequirementsSynthesis")

from ..common.utils import load_directory_context, save_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

requirements_synthesis_agent = ProcessLlmAgent(
    name="Requirements_Synthesis_Agent",
    description=(
        "Synthesizes a new, structured requirements register directly from a user's own "
        "description of a product/system/initiative plus general domain/regulatory knowledge, "
        "and saves it for the pipeline's own next stage to render as a document."
    ),
    instruction_file="common/requirements_synthesis_agent.txt",
    tools=[load_directory_context, save_requirements_summary],
)
