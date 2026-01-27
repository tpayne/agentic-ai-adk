# process_agents/grounding_agent.py

import yaml
import sys
import json
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
# TOOL: Load OpenAPI spec
# ---------------------------------------------------------
def load_openapi(tool_context=None):
    spec_path = Path(getProperty("OPENAPI_SPEC"))
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
# TOOL: OpenAPI Call Execution
# ---------------------------------------------------------
def perform_openapi_call(tool_context: ToolContext, request_json: str):
    """
    Executes an OpenAPI call based on a JSON request string.
    """
    try:
        request = json.loads(request_json)
    except Exception as e:
        return {"ok": False, "error": f"Invalid JSON: {e}"}

    spec = load_openapi()
    if "_empty" in spec:
        return {"ok": False, "error": "Spec unavailable"}

    # Extract the base URL from the first server object in the list
    servers = spec.get("servers", [])
    base_url = ""
    if servers and isinstance(servers, list):
        base_url = servers[0].get("url", "")
    
    # Ensure there is no double slash if the base_url ends with one and path starts with one
    path = request.get('path', '')
    params = request.get("params", {})

    for key in list(params.keys()):
        placeholder = "{" + key + "}"
        if placeholder in path:
            path = path.replace(placeholder, str(params[key]))
            params.pop(key)

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    # Use a clean User-Agent as requested
    headers = {
        "Accept": "application/json",
        "User-Agent": "ProcessEngine/1.0 (contact: your-email@example.com) Python-Requests"
    }

    try:
        method = request.get("method", "GET").upper()
        if method == "GET":
            # Remaining params not used in path are sent as query strings
            resp = requests.get(url, params=params, headers=headers, timeout=10)
        else:
            resp = requests.request(
                method,
                url,
                json=request.get("body"),
                headers=headers,
                timeout=10
            )

        resp.raise_for_status()
        response_data = resp.json()

        # FIXED: Added f-strings and json.dumps for readability
        logger.debug(f"Request callout: {request_json}")
        logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")
        
        return {"ok": True, "data": response_data}

    except Exception as e:
        logger.error(f"Perform OpenAPI call error: {str(e)}")
        return {"ok": False, "error": str(e)}

# ---------------------------------------------------------
# GROUNDING VALIDATION AGENT
# ---------------------------------------------------------
grounding_agent = LlmAgent(
    name="Grounding_Validation_Agent",
    model=getProperty("MODEL"),
    description="Validates a designed process against external reality.",
    include_contents="default",
    # REMOVED: output_key="grounding_report" 
    tools=[
        load_openapi,
        load_master_process_json,
        save_iteration_feedback,
        perform_openapi_call,
    ],
    instruction=load_instruction("grounding_agent.txt"),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)