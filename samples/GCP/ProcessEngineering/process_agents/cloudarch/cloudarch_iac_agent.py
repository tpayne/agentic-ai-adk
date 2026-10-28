# process_agents/cloudarch_iac_agent.py
from google.genai import types

import logging

logger = logging.getLogger("ProcessArchitect.CloudArchIac")

from ..common.utils import (
    load_drawio,
    load_iteration_feedback,
    save_iac_files,
)

# -----------------------------
# CLOUDARCH IAC AGENT DEFINITION
# -----------------------------
from ..common.agent_wrappers import ProcessLlmAgent
cloudarch_iac_agent = ProcessLlmAgent(
    name='CloudArch_IaC_Agent',
    description='Writes Infrastructure-as-Code files implementing the current cloud architecture diagram, in the language/tool requested.',
    instruction_file="cloudarch/cloudarch_iac_agent.txt",
    tools=[
        load_drawio,
        load_iteration_feedback,
        save_iac_files,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
