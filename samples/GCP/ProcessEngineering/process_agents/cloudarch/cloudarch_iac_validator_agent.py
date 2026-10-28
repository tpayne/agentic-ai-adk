# process_agents/cloudarch_iac_validator_agent.py
from google.genai import types

import logging

logger = logging.getLogger("ProcessArchitect.CloudArchIacValidator")

from ..common.utils import (
    validate_iac_files,
    save_iteration_feedback,
)

# -----------------------------
# CLOUDARCH IAC VALIDATOR AGENT DEFINITION
# -----------------------------
from ..common.agent_wrappers import ProcessLlmAgent
cloudarch_iac_validator_agent = ProcessLlmAgent(
    name='CloudArch_IaC_Validator_Agent',
    description='Validates the syntax of the Infrastructure-as-Code files CloudArch_IaC_Agent just wrote.',
    instruction_file="cloudarch/cloudarch_iac_validator_agent.txt",
    tools=[
        validate_iac_files,
        save_iteration_feedback,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
