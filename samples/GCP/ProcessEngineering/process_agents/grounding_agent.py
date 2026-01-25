# process_agents/grounding_agent.py

import yaml
import requests
from pathlib import Path
import logging

from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.tools.tool_context import ToolContext

from .utils import (
    load_instruction,
    load_master_process_json,
    save_iteration_feedback,
    getProperty
)

logger = logging.getLogger("ProcessArchitect.Grounding")


# ---------------------------------------------------------
# TOOL: Load OpenAPI spec (with graceful empty handling)
# ---------------------------------------------------------
def load_openapi(tool_context: ToolContext):
    """
    Returns the OpenAPI specification for the grounding agent.
    If missing or empty, returns {"_empty": True, "reason": "..."}.
    """
    spec_path = Path(tool_context.config["openapi_path"])

    if not spec_path.exists():
        return {"_empty": True, "reason": "missing"}

    try:
        with spec_path.open("r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except Exception as e:
        return {"_empty": True, "reason": f"invalid: {e}"}

    if not spec or "paths" not in spec or not spec["paths"]:
        return {"_empty": True, "reason": "no_paths"}

    return spec


# ---------------------------------------------------------
# PYTHON-SIDE EXECUTION OF OPENAPI CALLS
# ---------------------------------------------------------
def perform_openapi_call(tool_context: ToolContext, request: dict):
    """
    Executes an OpenAPI call requested by the LLM via an `openapi_call` JSON object.
    """
    spec = load_openapi(tool_context)
    logger.debug("Invoking an OpenAPI call {request}...")

    if isinstance(spec, dict) and spec.get("_empty"):
        return {"ok": False, "error": f"OpenAPI spec unavailable: {spec.get('reason')}"}

    server = spec["servers"][0]["url"]
    url = f"{server}{request['path']}"

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {tool_context.config.get('api_token', '')}"
    }

    try:
        logger.debug("Calling {url}...")
        if request["method"].upper() == "GET":
            resp = requests.get(url, params=request.get("params"), headers=headers, timeout=10)
        else:
            resp = requests.request(
                request["method"],
                url,
                json=request.get("body"),
                headers=headers,
                timeout=10
            )

        resp.raise_for_status()
        return {"ok": True, "data": resp.json()}

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------
# GROUNDING VALIDATION AGENT
# ---------------------------------------------------------
grounding_agent = LlmAgent(
    name="Grounding_Validation_Agent",
    model=getProperty("MODEL"),
    description="Validates a designed process against external reality using OpenAPI-defined sources of truth.",
    include_contents="default",
    output_key="grounding_report",
    tools=[
        load_openapi,
        load_master_process_json,
        save_iteration_feedback,
    ],
    instruction=load_instruction("grounding_agent.txt"),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
