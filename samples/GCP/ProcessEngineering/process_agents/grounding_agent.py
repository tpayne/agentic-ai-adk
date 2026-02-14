# process_agents/grounding_agent.py

import yaml
import sys
import json
import requests
import certifi
import time
import random

import logging
import os

from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.tools.tool_context import ToolContext

# NEW: import urllib3 and the warning class for conditional suppression
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from .utils import (
    load_master_process_json,
    save_iteration_feedback,
    getProperty,
)

# Conditionally suppress InsecureRequestWarning ONLY if you’ve explicitly allowed insecure HTTPS.
# Prefer setting a valid CA bundle so you can keep verification ON.  (See notes below.)
if str(getProperty("ALLOW_INSECURE_HTTPS", default=False)).lower() in ("1", "true", "yes"):
    urllib3.disable_warnings(InsecureRequestWarning)  # suppress only this warning

logger = logging.getLogger("ProcessArchitect.Grounding")

# ---------------------------------------------------------
# TOOL: Load OpenAPI spec
# ---------------------------------------------------------
def load_openapi(tool_context=None):
    spec_path = None
    try:
        openapi_spec = getProperty("OPENAPI_SPEC", default=None)
        if not openapi_spec:
            return {"_empty": True, "reason": "missing"}
        spec_path = Path(str(openapi_spec))
        if not spec_path.exists():
            return {"_empty": True, "reason": "missing"}
    except Exception as e:
        return {"_empty": True, "reason": f"invalid_path: {e}"}

    try:
        with spec_path.open("r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except Exception as e:
        return {"_empty": True, "reason": f"invalid: {e}"}

    if not spec or "paths" not in spec or not spec["paths"]:
        return {"_empty": True, "reason": "no_paths"}

    return spec

# ---------------------------------------------------------
# TOOL: OpenAPI Call Execution (HTTP retries with sleep + jitter)
# ---------------------------------------------------------

class JitterAdapter(HTTPAdapter):
    """
    Injects sleep between retries using your pattern:
      time.sleep(modelSleep + random.random() * 0.75 + backoff_sleep)
    Where:
      - backoff_sleep is the exponential backoff computed by urllib3.Retry
      - modelSleep is read from properties (defaults handled in getProperty)
    """
    def sleep(self, sleep_time: float):
        try:
            base = float(getProperty("modelSleep", default=0.25))  # your pattern baseline
        except Exception:
            base = 0.25
        jitter = random.random() * 0.75  # your pattern jitter
        adjusted = max(0.0, sleep_time + base + jitter)
        # Delegate to HTTPAdapter's default sleep (which calls time.sleep)
        return super().sleep(adjusted)

def _build_session():
    # Truncated exponential backoff; urllib3 computes sleep for each retry:
    #   sleep = backoff_factor * (2 ** (retry_num - 1))
    # With respect_retry_after_header=True, Retry will use server-provided Retry-After when present.
    # This is recommended for handling 429 bursts in Vertex/LLM workloads and general HTTP APIs. [1](https://developers.googleblog.com/building-agents-with-the-adk-and-the-new-interactions-api/)
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=0.4,                 # baseline; your adapter adds modelSleep + jitter on top
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        raise_on_status=False,
        respect_retry_after_header=True      # honor Retry-After if server sets it
    )

    sess = requests.Session()
    adapter = JitterAdapter(max_retries=retry)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)

    ua = getProperty(
        "USER_AGENT",
        default="ProcessArchitect/1.0 (contact: https://example.com/contact)"
    )
    sess.headers.update({
        "Accept": "application/json",
        "User-Agent": str(ua)  # Wikimedia requests a contactable UA
    })
    return sess

def _resolve_verify():
    ca_bundle = getProperty("REQUESTS_CA_BUNDLE") or getProperty("SSL_CERT_FILE")
    if ca_bundle and os.path.exists(str(ca_bundle)):
        return str(ca_bundle)
    return certifi.where()  # Mozilla bundle

def perform_openapi_call(tool_context: ToolContext, request_json: str):
    """
    Executes an OpenAPI call based on a JSON request string.
    """
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)

    try:
        request = json.loads(request_json)
    except Exception as e:
        return {"ok": False, "error": f"Invalid JSON: {e}"}

    spec = load_openapi()
    if "_empty" in spec:
        return {"ok": False, "error": "Spec unavailable"}

    servers = spec.get("servers", [])
    base_url = servers[0].get("url", "") if servers and isinstance(servers, list) else ""
    path = request.get("path", "")
    params = request.get("params", {}) or {}

    for key in list(params.keys()):
        placeholder = "{" + key + "}"
        if placeholder in path:
            path = path.replace(placeholder, str(params[key]))
            params.pop(key)

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    session = _build_session()
    verify = _resolve_verify()
    method = (request.get("method") or "GET").upper()
    body = request.get("body")

    tval = getProperty("HTTP_TIMEOUT_SECONDS", default=15)
    try:
        timeout = float(tval)
    except Exception:
        timeout = 15.0

    try:
        if method == "GET":
            resp = session.get(url, params=params, timeout=timeout, verify=verify)
        else:
            resp = session.request(method, url, json=body, timeout=timeout, verify=verify)

        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text, "content_type": resp.headers.get("Content-Type", "")}

        logger.debug(f"Request callout: {request_json}")
        logger.debug(json.dumps(data, indent=2))
        return {"ok": True, "data": data}

    except requests.exceptions.SSLError as ssl_err:
        allow_insecure = str(getProperty("ALLOW_INSECURE_HTTPS", default=False)).lower() in ("1", "true", "yes")
        if allow_insecure:
            logger.warning("TLS verification failed. Retrying with verify=False (INSECURE!)")
            try:
                time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
                if method == "GET":
                    resp = session.get(url, params=params, timeout=timeout, verify=False)
                else:
                    resp = session.request(method, url, json=body, timeout=timeout, verify=False)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except ValueError:
                    data = {"raw": resp.text, "content_type": resp.headers.get("Content-Type", "")}
                return {"ok": True, "data": data, "_insecure": True, "_warning": "verify=False used"}
            except Exception as e:
                logger.error(f"Insecure retry failed: {e}")
                return {"ok": False, "error": f"TLS error then insecure retry failed: {ssl_err}"}
        logger.error(f"TLS verification failed: {ssl_err}")
        return {"ok": False, "error": f"TLS verification failed: {ssl_err}"}

    except Exception as e:
        time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
        logger.error(f"Perform OpenAPI call error: {e}")
        return {"ok": False, "error": str(e)}

# ---------------------------------------------------------
# GROUNDING VALIDATION AGENT
# ---------------------------------------------------------
from .agent_wrappers import ProcessLlmAgent
grounding_agent = ProcessLlmAgent(
    name="Grounding_Validation_Agent",
    description="Validates a designed process against external reality.",
    include_contents="default",
    tools=[
        load_openapi,
        load_master_process_json,
        save_iteration_feedback,
        perform_openapi_call,
    ],
    instruction_file="grounding_agent.txt",
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)