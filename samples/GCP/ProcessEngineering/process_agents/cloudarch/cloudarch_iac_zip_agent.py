# process_agents/cloudarch_iac_zip_agent.py
from google.genai import types

import logging

logger = logging.getLogger("ProcessArchitect.CloudArchIacZip")

from ..common.utils import load_drawio, zip_iac_files
from ..common.utils_agent import download_artifact

# -----------------------------
# CLOUDARCH IAC ZIP/DOWNLOAD AGENT DEFINITION
# -----------------------------
# Final step of CloudArch_IaC_Pipeline, run after the generate/validate loop
# stops -- see cloudarch_iac_pipeline_agent.py's own comments for why this
# step must run regardless of the loop's stop reason (same MANDATORY-after-
# loop-STOP reasoning as design_doc_create_agent.py's own doc-build stage).
from ..common.agent_wrappers import ProcessLlmAgent
cloudarch_iac_zip_agent = ProcessLlmAgent(
    name='CloudArch_IaC_Zip_Agent',
    description='Zips the generated Infrastructure-as-Code files and makes them available to download.',
    instruction_file="cloudarch/cloudarch_iac_zip_agent.txt",
    tools=[
        zip_iac_files,
        load_drawio,
        download_artifact,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
