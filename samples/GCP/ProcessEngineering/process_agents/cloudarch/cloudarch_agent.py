# process_agents/compliance_agent.py
from google.genai import types

import logging
import time
import random
import os
import shutil

logger = logging.getLogger("ProcessArchitect.CloudArch")

from ..common.utils import (
    load_master_process_json,
    getProperty,
    save_drawio,
    save_drawio_structured,
    load_drawio,
    load_iteration_feedback,
    load_directory_context,
    load_requirements_summary,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def log_cloudarch_metadata(status: str):
    """Internal tool to report status."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"CloudArch Metadata - Status: {status},")
    return {}

# -----------------------------
# OPTIONAL: DRAWIO MCP SHAPE SEARCH
# -----------------------------
# Off by default. When enabled, gives CloudArch_Agent a "search_shapes" tool
# from the official draw.io MCP server (github.com/jgraph/drawio-mcp) to look
# up accurate platform-specific shape style strings before writing diagram
# XML. Only that one tool is exposed -- the server's other tools open a
# browser tab for a human to view/edit the diagram, which doesn't fit this
# pipeline's unattended runs. Diagram XML is still generated and persisted
# locally via save_drawio either way; this only improves icon accuracy.
_cloudarch_tools = [
    load_master_process_json,
    load_iteration_feedback,
    load_directory_context,
    load_requirements_summary,
    log_cloudarch_metadata,
    save_drawio_structured,
    save_drawio,
    load_drawio,
]

if getProperty("enableDrawioShapeSearch", default="false"):
    if shutil.which("npx") is None:
        logger.warning(
            "enableDrawioShapeSearch is on but 'npx' was not found on PATH -- "
            "the draw.io MCP server (npx -y @drawio/mcp) cannot be launched. "
            "Install Node.js, or set enableDrawioShapeSearch = False."
        )
    try:
        from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
        from mcp import StdioServerParameters

        _drawio_mcp_toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=["-y", "@drawio/mcp"],
                ),
                timeout=30.0,
            ),
            tool_filter=["search_shapes"],
        )
        _cloudarch_tools.append(_drawio_mcp_toolset)
    except ImportError:
        logger.warning(
            "enableDrawioShapeSearch is on but the 'mcp' package is not "
            "installed -- run `pip install mcp` (see requirements.txt), or "
            "set enableDrawioShapeSearch = False."
        )

# -----------------------------
# CLOUDARCH AGENT DEFINITION
# -----------------------------
from ..common.agent_wrappers import ProcessLlmAgent
cloudarch_agent = ProcessLlmAgent(
    name='CloudArch_Agent',
    description='Audits processes against sector best practices.',
    instruction_file="cloudarch/cloudarch_agent.txt",
    tools=_cloudarch_tools,
    generate_content_config=types.GenerateContentConfig(
        temperature=float(getProperty("cloudarchTemperature", default=0.1)),
        top_p=float(getProperty("cloudarchTopP", default=1)),
    ),
)
