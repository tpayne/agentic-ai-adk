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
# TOOL: Call an OpenAPI-defined endpoint
# ---------------------------------------------------------
def call_openapi(tool_context: ToolContext, path: str, method: str,
                 params: dict = None, body: dict = None):
    """
    Generic OpenAPI caller.

    The agent must supply:
      - path (e.g. "/entities")
      - method ("GET" or "POST")
      - params (dict for query parameters)
      - body (dict for JSON body)
    """

    spec = load_openapi(tool_context)

    # If spec is empty, return a safe error
    if isinstance(spec, dict) and spec.get("_empty"):
        return {
            "ok": False,
            "error": f"OpenAPI spec unavailable: {spec.get('reason')}",
            "path": path,
            "method": method,
            "params": params,
            "body": body,
        }

    server = spec["servers"][0]["url"]
    url = f"{server}{path}"

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {tool_context.config.get('api_token', '')}"
    }

    try:
        if method.upper() == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=10)
        else:
            resp = requests.request(method, url, json=body, headers=headers, timeout=10)

        resp.raise_for_status()

        return {
            "ok": True,
            "path": path,
            "method": method,
            "params": params,
            "body": body,
            "data": resp.json(),
        }

    except Exception as e:
        return {
            "ok": False,
            "path": path,
            "method": method,
            "params": params,
            "body": body,
            "error": str(e),
        }


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
        call_openapi,
        load_master_process_json,
        save_iteration_feedback,
    ],
    instruction=load_instruction("grounding_agent.txt"),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
