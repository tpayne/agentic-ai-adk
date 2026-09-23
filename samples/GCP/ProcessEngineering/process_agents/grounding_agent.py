# process_agents/grounding_agent.py

import yaml
import sys
import json
import re
import requests
import certifi
import time
import random

import logging
import os

from pathlib import Path
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.tools.tool_context import ToolContext

from .utils import (
    load_master_process_json,
    save_iteration_feedback,
    getProperty,
)

logger = logging.getLogger("ProcessArchitect.Grounding")


def _resolve_spec_base_url(spec: dict):
    """Return the server URL from the OpenAPI spec, or None if the spec is unusable."""
    servers = spec.get("servers", []) if isinstance(spec, dict) else []
    if not isinstance(servers, list) or not servers:
        return None

    for server in servers:
        if not isinstance(server, dict):
            continue
        url = str(server.get("url", "")).strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return url.rstrip("/")
    return None


def _path_matches_openapi_template(template: str, candidate: str) -> bool:
    """Allow only endpoints that exist in the OpenAPI path table for the called method."""
    if not template or not candidate:
        return False

    template = template.strip()
    candidate = candidate.strip()
    if not template.startswith("/"):
        template = "/" + template
    if not candidate.startswith("/"):
        candidate = "/" + candidate

    regex = re.escape(template)
    regex = regex.replace(r"\{", "{").replace(r"\}", "}")
    regex = re.sub(r"\{[^{}]+\}", r"[^/]+", regex)
    return re.fullmatch(regex, candidate) is not None


def _validate_requested_endpoint(spec: dict, method: str, path: str) -> bool:
    """Reject any path/method pair not explicitly present in the OpenAPI spec."""
    if not isinstance(spec, dict):
        return False

    method = (method or "GET").upper()
    spec_paths = spec.get("paths", {})
    if not isinstance(spec_paths, dict):
        return False

    for template, operations in spec_paths.items():
        if not isinstance(operations, dict):
            continue
        if method.lower() not in operations:
            continue
        if _path_matches_openapi_template(str(template), str(path)):
            return True
    return False

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
        # This agent only ever issues GET (see perform_openapi_call's method check below);
        # kept single-verb here too so a future change to the call path can't silently
        # regain write access to the upstream API via retry plumbing alone.
        allowed_methods=["GET"],
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

    base_url = _resolve_spec_base_url(spec)
    if not base_url:
        return {"ok": False, "error": "OpenAPI spec is missing a valid server URL"}

    method = (request.get("method") or "GET").upper()
    if method != "GET":
        # This agent's role is read-only fact-checking against a live system, never mutation.
        # The OpenAPI spec may legitimately declare POST/PUT/PATCH/DELETE operations for other
        # consumers of that API -- that does not make them safe for an automated grounding pass
        # to invoke. Reject every non-GET verb outright, regardless of what the spec allows.
        return {"ok": False, "error": f"Method not permitted for grounding calls (read-only): {method}"}
    path = str(request.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "Request path is required"}

    params = request.get("params", {}) or {}
    if not isinstance(params, dict):
        return {"ok": False, "error": "Request params must be an object"}

    for key in list(params.keys()):
        placeholder = "{" + key + "}"
        if placeholder in path:
            path = path.replace(placeholder, str(params[key]))
            params.pop(key)

    if not _validate_requested_endpoint(spec, method, path):
        return {"ok": False, "error": f"Endpoint not allowed by OpenAPI spec: {method} {path}"}

    url = f"{base_url}/{path.lstrip('/')}"

    session = _build_session()
    verify = _resolve_verify()

    tval = getProperty("HTTP_TIMEOUT_SECONDS", default=15)
    try:
        timeout = float(tval)
    except Exception:
        timeout = 15.0

    try:
        # allow_redirects=False: a redirect response is never auto-followed. Following one
        # blindly would let the upstream server hand this agent a different URL entirely --
        # including one outside the OpenAPI spec's declared server -- bypassing the endpoint
        # allowlist above. A redirect is treated as a failed call instead (see below).
        resp = session.get(url, params=params, timeout=timeout, verify=verify, allow_redirects=False)

        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location", "")
            logger.error(f"Refusing to follow redirect from {url} to {location}")
            return {"ok": False, "error": f"Endpoint returned a redirect, which is not followed: {resp.status_code}"}

        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text, "content_type": resp.headers.get("Content-Type", "")}

        logger.debug(f"Request callout: {request_json}")
        logger.debug(json.dumps(data, indent=2))
        return {"ok": True, "data": data}

    except requests.exceptions.SSLError as ssl_err:
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