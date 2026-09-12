# process_agents/utils.py
import os
import json
import glob
import time
import random
import re
import traceback
import logging
import configparser
from typing import Any, Union

from typing import Optional

from google.adk.models import LlmResponse, LlmRequest
from google.adk.agents import callback_context
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

logger = logging.getLogger("ProcessArchitect.Utils")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ============================================================
# ANSI COLOR CONSTANTS
# ============================================================
ANSI_RESET = "\033[0m"
ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_BLUE = "\033[94m"
ANSI_CYAN = "\033[96m"

# Standard (non-bright) foreground colors
ANSI_BLACK = "\033[30m"
ANSI_RED_NORMAL = "\033[31m"
ANSI_GREEN_NORMAL = "\033[32m"
ANSI_YELLOW_NORMAL = "\033[33m"
ANSI_BLUE_NORMAL = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN_NORMAL = "\033[36m"
ANSI_WHITE = "\033[37m"

# Bright foreground colors
ANSI_BRIGHT_BLACK = "\033[90m"
ANSI_BRIGHT_RED = "\033[91m"
ANSI_BRIGHT_GREEN = "\033[92m"
ANSI_BRIGHT_YELLOW = "\033[93m"
ANSI_BRIGHT_BLUE = "\033[94m"
ANSI_BRIGHT_MAGENTA = "\033[95m"
ANSI_BRIGHT_CYAN = "\033[96m"
ANSI_BRIGHT_WHITE = "\033[97m"

# Background colors (standard)
ANSI_BG_BLACK = "\033[40m"
ANSI_BG_RED = "\033[41m"
ANSI_BG_GREEN = "\033[42m"
ANSI_BG_YELLOW = "\033[43m"
ANSI_BG_BLUE = "\033[44m"
ANSI_BG_MAGENTA = "\033[45m"
ANSI_BG_CYAN = "\033[46m"
ANSI_BG_WHITE = "\033[47m"

# Background colors (bright)
ANSI_BG_BRIGHT_BLACK = "\033[100m"
ANSI_BG_BRIGHT_RED = "\033[101m"
ANSI_BG_BRIGHT_GREEN = "\033[102m"
ANSI_BG_BRIGHT_YELLOW = "\033[103m"
ANSI_BG_BRIGHT_BLUE = "\033[104m"
ANSI_BG_BRIGHT_MAGENTA = "\033[105m"
ANSI_BG_BRIGHT_CYAN = "\033[106m"
ANSI_BG_BRIGHT_WHITE = "\033[107m"

# Text styles
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_UNDERLINE = "\033[4m"
ANSI_BLINK = "\033[5m"
ANSI_REVERSE = "\033[7m"
ANSI_HIDDEN = "\033[8m"

# Internal cache
_CACHE: Union[configparser.ConfigParser, None] = None
PROPERTIES_FILE = os.path.join(PROJECT_ROOT, 'properties', 'agentapp.properties')

def getProperty(prop: str, section: str = 'SETTINGS',
                default: Union[str, int, float, bool, None] = None) -> Any:
    global _CACHE
    if _CACHE is None:
        # One-time disk read with error handling for path
        config = configparser.ConfigParser()
        if os.path.exists(PROPERTIES_FILE):
            config.read(PROPERTIES_FILE)
        _CACHE = config

    try:
        val = _CACHE.get(section, prop)
    except (configparser.NoOptionError, configparser.NoSectionError):
        # Fallback to environment variable
        env_val = os.getenv(prop)
        if env_val is not None:
            val = env_val
        else:
            return default

    # Clean up quotes (e.g., "5" -> 5)
    val = val.strip('"').strip("'")

    # Boolean conversion
    val_lower = val.lower()
    if val_lower in ['true', 'yes', 'on']:
        return True
    if val_lower in ['false', 'no', 'off']:
        return False

    # Integer conversion
    try:
        return int(val)
    except ValueError:
        pass

    # Float conversion
    try:
        return float(val)
    except ValueError:
        pass

    # Default: string (or default if empty)
    return val if val != '' else default

# ---------------------------------------------------------------------
# INTERNAL HELPERS (NOT EXPOSED TO LLM)
# ---------------------------------------------------------------------
import re

# Build a lookup table from your constants
ANSI_MAP = {
    "reset": ANSI_RESET,
    "red": ANSI_RED,
    "green": ANSI_GREEN,
    "yellow": ANSI_YELLOW,
    "blue": ANSI_BLUE,
    "cyan": ANSI_CYAN,

    "black_normal": ANSI_BLACK,
    "red_normal": ANSI_RED_NORMAL,
    "green_normal": ANSI_GREEN_NORMAL,
    "yellow_normal": ANSI_YELLOW_NORMAL,
    "blue_normal": ANSI_BLUE_NORMAL,
    "magenta": ANSI_MAGENTA,
    "cyan_normal": ANSI_CYAN_NORMAL,
    "white": ANSI_WHITE,

    "bright_black": ANSI_BRIGHT_BLACK,
    "bright_red": ANSI_BRIGHT_RED,
    "bright_green": ANSI_BRIGHT_GREEN,
    "bright_yellow": ANSI_BRIGHT_YELLOW,
    "bright_blue": ANSI_BRIGHT_BLUE,
    "bright_magenta": ANSI_BRIGHT_MAGENTA,
    "bright_cyan": ANSI_BRIGHT_CYAN,
    "bright_white": ANSI_BRIGHT_WHITE,

    "bg_black": ANSI_BG_BLACK,
    "bg_red": ANSI_BG_RED,
    "bg_green": ANSI_BG_GREEN,
    "bg_yellow": ANSI_BG_YELLOW,
    "bg_blue": ANSI_BG_BLUE,
    "bg_magenta": ANSI_BG_MAGENTA,
    "bg_cyan": ANSI_BG_CYAN,
    "bg_white": ANSI_BG_WHITE,

    "bg_bright_black": ANSI_BG_BRIGHT_BLACK,
    "bg_bright_red": ANSI_BG_BRIGHT_RED,
    "bg_bright_green": ANSI_BG_BRIGHT_GREEN,
    "bg_bright_yellow": ANSI_BG_BRIGHT_YELLOW,
    "bg_bright_blue": ANSI_BG_BRIGHT_BLUE,
    "bg_bright_magenta": ANSI_BG_BRIGHT_MAGENTA,
    "bg_bright_cyan": ANSI_BG_BRIGHT_CYAN,
    "bg_bright_white": ANSI_BG_BRIGHT_WHITE,

    "bold": ANSI_BOLD,
    "dim": ANSI_DIM,
    "underline": ANSI_UNDERLINE,
    "blink": ANSI_BLINK,
    "reverse": ANSI_REVERSE,
    "hidden": ANSI_HIDDEN,
}

def _normalise(s: str) -> str:
    """Normalise input for matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower())

def getResponseColour(code: str = "responseColourInfo") -> str:
    """Return the best ANSI match for RESPONSE_TEXT."""
    raw = getProperty(code)
    if not raw:
        return None

    key = _normalise(raw)

    # 1. Exact match
    if key in ANSI_MAP:
        return ANSI_MAP[key]

    # 2. Partial match (e.g., "brightred" → "bright_red")
    for name, code in ANSI_MAP.items():
        if key in _normalise(name):
            return code

    # 3. Colour-only match (e.g., "red" → ANSI_RED)
    for name, code in ANSI_MAP.items():
        if key in name:
            return code

    # 4. Fallback
    return ANSI_RESET

def _safe_sleep_from_property(name: str, default: float = 0.25):
    pv = getProperty(name, default=default)
    try:
        base = float(pv)
    except Exception:
        base = default
    time.sleep(base + random.random() * 0.75)

def _log_agent_activity(message: str):
    """Internal logging helper."""
    _safe_sleep_from_property("modelSleep", default=0.25)
    logger.debug(f"--- [DIAGNOSTIC] Utils: {message} ---")

def _extract_json_brace_balanced(text: str) -> str:
    """
    Extract the FIRST valid JSON object from a text blob using brace counting.
    Handles reviewer prefixes like 'JSON APPROVED' or 'REVISION REQUIRED'.
    """
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in text")

    brace_count = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                return text[start:i+1]

    raise ValueError("JSON braces not balanced")

def _validate_process_json(data: dict):
    """
    Returns:
      - [] if valid
      - list of issue objects if invalid
      - None only if data is not a dict
    """
    if not isinstance(data, dict):
        logger.error("Process JSON does not contain a JSON object.")
        return None

    issues = []

    required_top_keys = [
        "process_name",
        "industry_sector",
        "version",
        "introduction",
        "stakeholders",
        "process_steps",
        "tools_summary",
        "metrics",
        "critical_success_factors",
        "critical_failure_factors",
        "reporting_and_analytics",
        "system_requirements",
        "assumptions",
        "constraints",
        "appendix",
        "purpose",
        "scope",
        "process_owner",
        "process_triggers",
        "process_end_conditions",
        "risks_and_controls",
        "governance_requirements",
        "change_management",
        "continuous_improvement",
    ]

    # --- Top-level validation ---
    for key in required_top_keys:
        if key not in data:
            issues.append({
                "location": f"$.{key}",
                "issue": f"Missing required top-level key '{key}'"
            })

    # If top-level keys missing, no need to continue deeper
    if issues:
        return issues

    # --- process_name ---
    if not isinstance(data.get("process_name"), str) or not data["process_name"].strip():
        issues.append({
            "location": "$.process_name",
            "issue": "Invalid or empty 'process_name'"
        })

    # --- process_steps ---
    if not isinstance(data.get("process_steps"), list) or len(data["process_steps"]) == 0:
        issues.append({
            "location": "$.process_steps",
            "issue": "Invalid or empty 'process_steps'"
        })
        return issues

    required_step_keys = [
        "step_name",
        "description",
        "responsible_party",
        "estimated_duration",
        "deliverables",
        "inputs",
        "outputs",
        "dependencies",
        "success_criteria"
    ]

    for idx, step in enumerate(data["process_steps"]):
        if not isinstance(step, dict):
            issues.append({
                "location": f"$.process_steps[{idx}]",
                "issue": "Step is not an object"
            })
            continue

        for sk in required_step_keys:
            if sk not in step:
                issues.append({
                    "location": f"$.process_steps[{idx}].{sk}",
                    "issue": f"Missing required step key '{sk}'"
                })

    return issues


def save_drawio(xml_content) -> str:
    """
    Persists a validated DrawIO XML document to output/cloudarch_drawio.xml.
    Includes lock protection, validation, unchanged-file detection, and
    a provider-aware shape + container mapping pass for Azure, AWS, and GCP.
    Shared helpers (_log_agent_activity, _safe_sleep_from_property, etc.)
    are assumed to exist in the environment.
    """

    # --- HYBRID SHAPE MAPPINGS (EXTENSIBLE) ---

    # Service icons (mxgraph.*)

    AZURE_SHAPES = {
        # Networking
        "application gateway": "img/lib/azure2/networking/Application_Gateways.svg",
        "application gateways": "img/lib/azure2/networking/Application_Gateways.svg",
        "application gateway containers": "img/lib/azure2/networking/Application_Gateway_Containers.svg",
        "azure firewall manager": "img/lib/azure2/networking/Azure_Firewall_Manager.svg",
        "azure firewall policy": "img/lib/azure2/networking/Azure_Firewall_Policy.svg",
        "bastion": "img/lib/azure2/networking/Bastions.svg",
        "bastions": "img/lib/azure2/networking/Bastions.svg",
        "dns private resolver": "img/lib/azure2/networking/DNS_Private_Resolver.svg",
        "dns security policy": "img/lib/azure2/networking/DNS_Security_Policy.svg",
        "dns zones": "img/lib/azure2/networking/DNS_Zones.svg",
        "expressroute circuits": "img/lib/azure2/networking/Expressroute_Circuits.svg",
        "firewalls": "img/lib/azure2/networking/Firewalls.svg",
        "front door": "img/lib/azure2/networking/Front_Doors.svg",
        "front doors": "img/lib/azure2/networking/Front_Doors.svg",
        "ip address manager": "img/lib/azure2/networking/IP_Address_Manager.svg",
        "private link hub": "img/lib/azure2/networking/Private_Link_Hub.svg",
        "service endpoint policies": "img/lib/azure2/networking/Service_Endpoint_Policies.svg",
        "virtual wan hub": "img/lib/azure2/networking/Virtual_Wan_Hub.svg",
        "virtual wans": "img/lib/azure2/networking/Virtual_Wans.svg",
        "vpn gateway": "img/lib/azure2/networking/Virtual_Network_Gateways.svg",

        # Compute
        "availability sets": "img/lib/azure2/compute/Availability_Sets.svg",
        "batch accounts": "img/lib/azure2/compute/Batch_Accounts.svg",
        "container instances": "img/lib/azure2/compute/Container_Instances.svg",
        "container services": "img/lib/azure2/compute/Container_Services.svg",
        "disk encryption sets": "img/lib/azure2/compute/Disk_Encryption_Sets.svg",
        "disks": "img/lib/azure2/compute/Disks.svg",
        "image templates": "img/lib/azure2/compute/Image_Templates.svg",
        "images": "img/lib/azure2/compute/Images.svg",
        "kubernetes services": "img/lib/azure2/compute/Kubernetes_Services.svg",
        "virtual machine": "img/lib/azure2/compute/Virtual_Machine.svg",
        "virtual machines": "img/lib/azure2/compute/Virtual_Machine.svg",
        "vm ": "img/lib/azure2/compute/Virtual_Machine.svg",
        " vm": "img/lib/azure2/compute/Virtual_Machine.svg",
        "vm scale sets": "img/lib/azure2/compute/VM_Scale_Sets.svg",

        # Storage / Data
        "adls gen1": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "adls gen2": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",  # corrected to Gen1 image
        "data lake": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "data lake storage": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "data lake store gen1": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "data lake storage gen1": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "data lake store gen2": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "data lake storage gen2": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "sql database": "img/lib/azure2/databases/SQL_Database.svg",
        "sql server": "img/lib/azure2/databases/SQL_Server.svg",
        "sql stretch database": "img/lib/azure2/databases/Azure_SQL_Server_Stretch_Databases.svg",
        "sql vm": "img/lib/azure2/databases/Azure_SQL_VM.svg",
        "sql managed instance": "img/lib/azure2/databases/SQL_Managed_Instance.svg",
        "sql elastic pools": "img/lib/azure2/databases/SQL_Elastic_Pools.svg",
        "instance pools": "img/lib/azure2/databases/Instance_Pools.svg",
        "oracle database": "img/lib/azure2/databases/Oracle_Database.svg",
        "azure data explorer clusters": "img/lib/azure2/databases/Azure_Data_Explorer_Clusters.svg",

        # AI / ML
        "ai studio": "img/lib/azure2/ai_machine_learning/AI_Studio.svg",
        "anomaly detector": "img/lib/azure2/ai_machine_learning/Anomaly_Detector.svg",
        "applied ai": "img/lib/azure2/ai_machine_learning/Azure_Applied_AI_Services.svg",
        "batch ai": "img/lib/azure2/ai_machine_learning/Batch_AI.svg",
        "bonsai": "img/lib/azure2/ai_machine_learning/Bonsai.svg",
        "bot services": "img/lib/azure2/ai_machine_learning/Bot_Services.svg",
        "cognitive services": "img/lib/azure2/ai_machine_learning/Cognitive_Services.svg",
        "computer vision": "img/lib/azure2/ai_machine_learning/Computer_Vision.svg",
        "content moderators": "img/lib/azure2/ai_machine_learning/Content_Moderators.svg",
        "content safety": "img/lib/azure2/ai_machine_learning/Content_Safety.svg",
        "language understanding": "img/lib/azure2/ai_machine_learning/Language_Understanding.svg",
        "azure openai": "img/lib/azure2/ai_machine_learning/Azure_OpenAI.svg",
        "machine learning studio workspaces": "img/lib/azure2/ai_machine_learning/Machine_Learning_Studio_Workspaces.svg",
        "speech services": "img/lib/azure2/ai_machine_learning/Speech_Services.svg",
        "translator text": "img/lib/azure2/ai_machine_learning/Translator_Text.svg",

        # Analytics
        "analysis services": "img/lib/azure2/analytics/Analysis_Services.svg",
        "azure databricks": "img/lib/azure2/analytics/Azure_Databricks.svg",
        "data factory": "img/lib/azure2/analytics/Data_Factories.svg",
        "data lake analytics": "img/lib/azure2/analytics/Data_Lake_Analytics.svg",
        "endpoint analytics": "img/lib/azure2/analytics/Endpoint_Analytics.svg",
        "event hub clusters": "img/lib/azure2/analytics/Event_Hub_Clusters.svg",
        "event hubs": "img/lib/azure2/analytics/Event_Hubs.svg",
        "log analytics workspaces": "img/lib/azure2/analytics/Log_Analytics_Workspaces.svg",
        "stream analytics jobs": "img/lib/azure2/analytics/Stream_Analytics_Jobs.svg",
        "synapse analytics": "img/lib/azure2/analytics/Azure_Synapse_Analytics.svg",
        "azure workbooks": "img/lib/azure2/analytics/Azure_Workbooks.svg",

        # App Services
        "api management services": "img/lib/azure2/app_services/API_Management_Services.svg",
        "app service certificates": "img/lib/azure2/app_services/App_Service_Certificates.svg",
        "app service domains": "img/lib/azure2/app_services/App_Service_Domains.svg",
        "app service environments": "img/lib/azure2/app_services/App_Service_Environments.svg",
        "app service plans": "img/lib/azure2/app_services/App_Service_Plans.svg",
        "app services": "img/lib/azure2/app_services/App_Services.svg",
        "cdn profiles": "img/lib/azure2/app_services/CDN_Profiles.svg",
        "notification hubs": "img/lib/azure2/app_services/Notification_Hubs.svg",
        "search services": "img/lib/azure2/app_services/Search_Services.svg",

        # Security / Identity
        "active directory": "img/lib/azure2/identity/Azure_Active_Directory.svg",
        "entra id": "img/lib/azure2/identity/Azure_Active_Directory.svg",
        "entra connect": "img/lib/azure2/identity/Entra_Connect.svg",
        "entra domain services": "img/lib/azure2/identity/Entra_Domain_Services.svg",
        "entra global secure access": "img/lib/azure2/identity/Entra_Global_Secure_Access.svg",
        "entra id protection": "img/lib/azure2/identity/Entra_ID_Protection.svg",
        "entra internet access": "img/lib/azure2/identity/Entra_Internet_Access.svg",
        "entra managed identities": "img/lib/azure2/identity/Entra_Managed_Identities.svg",
        "entra private access": "img/lib/azure2/identity/Entra_Private_Access.svg",
        "entra pim": "img/lib/azure2/identity/Entra_Privileged_Identity_Management.svg",
        "entra verified id": "img/lib/azure2/identity/Entra_Verified_ID.svg",
        "entra identity": "img/lib/azure2/identity/Entra_Identity.svg",
        "active directory connect health": "img/lib/azure2/identity/Active_Directory_Connect_Health.svg",
        "azure defender": "img/lib/azure2/security/Microsoft_Defender_for_Cloud.svg",
        "defender": "img/lib/azure2/security/Microsoft_Defender_for_Cloud.svg",
        "defender easm": "img/lib/azure2/security/Microsoft_Defender_EASM.svg",
        "dependency monitor": "img/lib/azure2/security/Dependency_Monitor.svg",
        "key vault": "img/lib/azure2/security/Key_Vaults.svg",
        "tenant key": "img/lib/azure2/security/Tenant_Key.svg",
        "key": "img/lib/azure2/security/Key.svg",

        # Governance / Monitoring
        "activity log": "img/lib/azure2/management_governance/Activity_Log.svg",
        "diagnostic settings": "img/lib/azure2/management_governance/Diagnostics_Settings.svg",
        "metrics": "img/lib/azure2/management_governance/Metrics.svg",
        "monitor": "img/lib/azure2/management_governance/Monitor.svg",
        "network watcher": "img/lib/azure2/networking/Network_Watcher.svg",
        "sap azure monitor": "img/lib/azure2/management_governance/SAP_Azure_Monitor.svg",
        "scale set": "img/lib/azure2/compute/VM_Scale_Sets.svg",
        "scale": "img/lib/azure2/compute/VM_Scale_Sets.svg",
    }

    AWS_SHAPES = {
        # Networking
        "vpn gateway": "mxgraph.aws3.vpn_gateway",
        "vpn connection": "mxgraph.aws3.vpn_connection",
        "client vpn": "mxgraph.aws4.client_vpn",
        "site to site vpn": "mxgraph.aws4.site_to_site_vpn",
        "vpc": "mxgraph.aws4.vpc",
        "vpc nat gateway": "mxgraph.aws4.nat_gateway",
        "vpc peering": "mxgraph.aws4.peering",
        "elastic network interface": "mxgraph.aws4.elastic_network_interface",
        "elastic network adapter": "mxgraph.aws4.elastic_network_adapter",
        "network acl": "mxgraph.aws4.network_access_control_list",
        "cloud wan virtual pop": "mxgraph.aws4.cloud_wan_virtual_pop",

        # Compute
        "emr cluster": "mxgraph.aws4.emr",
    }

    GCP_VERIFIED_ICONS = {
        # Real, confirmed-correct Google-sourced SVG icons extracted directly
        # from an authentic Google Cloud Architecture Diagramming Tool export
        # (user-provided ground truth). Values are complete embedded base64 SVG
        # data URIs -- guaranteed to render correctly, unlike GCP_SHAPES below
        # (unverified mxgraph.gcp2.<name> stencil-name guesses). Checked FIRST,
        # with priority over GCP_SHAPES, in _apply_shape_mappings.
        'advanced solutions lab': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE2Ljk3OTk5OTU0MjIzNjMyOCIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDE2Ljk3OTk5OTU0MjIzNjMyOCAyMCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MXtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDJ7ZmlsbDojYWVjYmZhO30mI3hhOwk8L3N0eWxlPiYjeGE7CTxnIGNsYXNzPSJzdDAiPiYjeGE7CQk8cGF0aCBkPSJNOC40OSAxMC4yOUwuMjQgNS4zNSA4LjQ5LjU4bDguMjQgNC42N3pNMS43NiA1LjM2bDYuNzIgNCA2LjcyLTQuMTEtNi43MS0zLjc4eiIvPiYjeGE7CQk8cGF0aCBkPSJNOC40OSAxOS40NEwuMjEgMTMuODkgOC40OSA5LjNsOC4xNSA0LjY0em0tNi44LTUuNWw2LjggNC41NiA2LjctNC41LTYuNy0zLjgyeiIvPiYjeGE7CTwvZz4mI3hhOwk8ZyBjbGFzcz0ic3QxIj4mI3hhOwkJPHBhdGggZD0iTS42MTMgNS41MDJsLjY3NS0uMzcxIDcuNDc3IDEzLjYtLjY3NS4zNzF6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik04LjE5NCAxOC44MjZsNy4zMDEtMTMuNTU5LjY3OC4zNjUtNy4zMDEgMTMuNTU5ek0uNzE2IDEzLjY4N0w4LjA5Ni45MDRsLjY2Ny4zODUtNy4zOCAxMi43ODN6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik04LjE5NCAxLjIxNGwuNjY5LS4zODEgNy40MDUgMTIuOTg3LS42NjkuMzgxeiIvPiYjeGE7CQk8cGF0aCBkPSJNOC4xMy45NmguNzdWMTguOWgtLjc3ek0uNTUgNS40M2guNzd2OC42NkguNTV6bTE0Ljk3LS4wOWguNzdWMTRoLS43N3oiLz4mI3hhOwk8L2c+JiN4YTsJPGcgY2xhc3M9InN0MiI+JiN4YTsJCTxjaXJjbGUgY3g9IjguNTIiIGN5PSIxLjA3IiByPSIxLjA3Ii8+JiN4YTsJCTxjaXJjbGUgY3g9IjE1LjkxIiBjeT0iNS4zNCIgcj0iMS4wNyIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIxLjA3IiBjeT0iNS4zNCIgcj0iMS4wNyIvPiYjeGE7CQk8Y2lyY2xlIGN4PSI4LjUyIiBjeT0iOS45MyIgcj0iMS42OCIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIxNS45MSIgY3k9IjEzLjk0IiByPSIxLjA3Ii8+JiN4YTsJCTxjaXJjbGUgY3g9IjEuMDciIGN5PSIxMy45NCIgcj0iMS4wNyIvPiYjeGE7CQk8Y2lyY2xlIGN4PSI4LjUyIiBjeT0iMTguOTMiIHI9IjEuMDciLz4mI3hhOwkJPHBhdGggZD0iTTguNDkgMTAuMjlMLjI0IDUuMzUgOC40OS41OGw4LjI0IDQuNjd6TTEuNzYgNS4zNmw2LjcyIDQgNi43Mi00LjExLTYuNzEtMy43OHoiLz4mI3hhOwkJPHBhdGggZD0iTTguNDkgMTkuNDRMLjIxIDEzLjg5IDguNDkgOS4zbDguMTUgNC42NHptLTYuOC01LjVsNi44IDQuNTYgNi43LTQuNS02LjctMy44MnoiLz4mI3hhOwkJPHBhdGggZD0iTS42MTMgNS41MDJsLjY3NS0uMzcxIDcuNDc3IDEzLjYtLjY3NS4zNzF6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik04LjE5NCAxOC44MjZsNy4zMDEtMTMuNTU5LjY3OC4zNjUtNy4zMDEgMTMuNTU5ek0uNzE2IDEzLjY4N0w4LjA5Ni45MDRsLjY2Ny4zODUtNy4zOCAxMi43ODN6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik04LjE5NCAxLjIxNGwuNjY5LS4zODEgNy40MDUgMTIuOTg3LS42NjkuMzgxeiIvPiYjeGE7CQk8cGF0aCBkPSJNOC4xMy45NmguNzdWMTguOWgtLjc3ek0uNTUgNS40M2guNzd2OC42NkguNTV6bTE0Ljk3LS4wOWguNzdWMTRoLS43N3oiLz4mI3hhOwk8L2c+JiN4YTsJPGcgY2xhc3M9InN0MCI+JiN4YTsJCTxjaXJjbGUgY3g9IjguNTIiIGN5PSIxLjA3IiByPSIxLjA3Ii8+JiN4YTsJCTxjaXJjbGUgY3g9IjE1LjkxIiBjeT0iNS4zNCIgcj0iMS4wNyIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIxLjA3IiBjeT0iNS4zNCIgcj0iMS4wNyIvPiYjeGE7CQk8Y2lyY2xlIGN4PSI4LjUyIiBjeT0iOS45MyIgcj0iMS42OCIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIxNS45MSIgY3k9IjEzLjk0IiByPSIxLjA3Ii8+JiN4YTsJCTxjaXJjbGUgY3g9IjEuMDciIGN5PSIxMy45NCIgcj0iMS4wNyIvPiYjeGE7CQk8Y2lyY2xlIGN4PSI4LjUyIiBjeT0iMTguOTMiIHI9IjEuMDciLz4mI3hhOwk8L2c+JiN4YTs8L3N2Zz4=',
        'agent assist': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGhlaWdodD0iMzY3LjgxODMyODg1NzQyMTkiIHZpZXdCb3g9IjcuMTA1NDI3MzU3NjAxMDAyZS0xNSAwIDM2Ni40MTAxODY3Njc1NzgxIDM2Ny44MTgzMjg4NTc0MjE5IiBwcmVzZXJ2ZUFzcGVjdFJhdGlvPSJ4TWlkWU1pZCBtZWV0IiB3aWR0aD0iMzY2LjQxMDE5Njc2NzU3OTEiIHZlcnNpb249IjEuMSIgaWQ9InN2Zzk4NyIgem9vbUFuZFBhbj0ibWFnbmlmeSI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4JLnN0MHtmaWxsOiM0Mjg1ZjQ7fQk8L3N0eWxlPgkmI3hhOyAgPHBhdGggY2xhc3M9InN0MCIgZD0ibSA0OC4yNTE5NiwxMTEuNTM5MDYgYyAtNy42MTg2NCwyZS00IC0xMy43OTQ3Miw2LjE3NjI4IC0xMy43OTQ5MywxMy43OTQ5MiAyLjFlLTQsNy42MTg2NCA2LjE3NjI5LDEzLjc5NDcyIDEzLjc5NDkzLDEzLjc5NDkyIGggMTQ1LjE0NjkyIHYgLTI3LjU4OTg0IHogbSAyMzguNjA4NTksNTcuNDUxMTcgaCA2NS43NTQ2OSBjIDcuNjE4NjQsLTIuMWUtNCAxMy43OTQ3MSwtNi4xNzYyOCAxMy43OTQ5MiwtMTMuNzk0OTIgLTIuMWUtNCwtNy42MTg2NCAtNi4xNzYyOCwtMTMuNzk0NzEgLTEzLjc5NDkyLC0xMy43OTQ5MiBIIDI4NC44NTA2IFogTSAxMy43OTQ5MiwxNzAuOTc0NjEgQyA2LjE3NjI4MDEsMTcwLjk3NDgyIDIuMTAwOTE5ZS00LDE3Ny4xNTA4OSA5LjE4OTkyMWUtOCwxODQuNzY5NTMgLTguNjk5MDgxZS00LDE5Mi4zODg5MyA2LjE3NTUyMDEsMTk4LjU2NjE5IDEzLjc5NDkyLDE5OC41NjY0IEggMTkzLjM5ODg4IFYgMTcwLjk3NDYxIFogTSAyODQuMzA3OCwyMjcuNTY2NCBoIDY4LjMwNzQ0IGMgNy42MTg2NCwtMi4xZS00IDEzLjc5NDcxLC02LjE3NjI4IDEzLjc5NDkyLC0xMy43OTQ5MiAtMi4xZS00LC03LjYxODY0IC02LjE3NjI4LC0xMy43OTQ3MSAtMTMuNzk0OTIsLTEzLjc5NDkyIGggLTY1LjkyMTc4IHogbSAtMjM2LjA1NTg0LDEuNjk3MjcgYyAtNy42MTg2NCwyZS00IC0xMy43OTQ3Miw2LjE3NjI4IC0xMy43OTQ5MywxMy43OTQ5MiAyLjFlLTQsNy42MTg2NCA2LjE3NjI5LDEzLjc5NDcyIDEzLjc5NDkzLDEzLjc5NDkyIEggMTkzLjM5ODg4IFYgMjI5LjI2MzY3IFogTSAxODkuNTIxNDksMCBjIC0yNC41NzQxMSwwIC00OS4xNjczNywyMC4wNTUwNyAtNTkuNDM3NSw3NS4zNzMwNCBoIDMwLjU4MDA3IGMgNC42MTYzMywtMjQuMTYyMDYgMTUuMzQ4OTYsLTQ3LjUyMTQ4IDI3Ljg1MzUyLC00Ny41MjE0OCAxMi4xNTg4LDAgMzkuNDU4OTgsNTcuNDUwNDQgMzkuNDU4OTgsMTYwLjQxNDA2IDAsNjkuOTE1MTMgLTE5LjU3ODA5LDE1Mi4xMTUyNCAtNDEuMTcxODcsMTUyLjExNTIzIC0xNS4yNjg4MSwyZS01IC0yMS4yMTY2OCwtMjguMzMzNTYgLTI1LjQ0MzM2LC00Ni43MTg3NCBsIC0zMC40MTQwNiwtMC4wNjg0IGMgNC4yMjA3NCwyMC41NDA4NyAxNi45MDc2OCw3NC4yMjQ2IDU3LjcxMjg5LDc0LjIyNDYgNTMuNDM2NzIsMCA2OC45MTIxMSwtMTExLjk5MzA1IDY4LjkxMjExLC0xODAuNDYyODkgQyAyNTcuNTcyMjcsOTMuODAwNzYgMjM2LjU4MzQsMCAxODkuNTIxNDksMCBaIi8+JiN4YTs8L3N2Zz4=',
        'ai hub': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM2Mi4yMjI0NzgzNzUzNTMxNSIgaGVpZ2h0PSIzNzcuMzU5NDg0NzI1NTkyNSIgdmlld0JveD0iNjcuMzQ3OTk5NTcyNzUzOSAxMDguNjg4MDAzNTQwMDM5MDYgOTUuODM4MDA1MDY1OTE3OTcgOTkuODQzMDAyMzE5MzM1OTQiPiYjeGE7PHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MXtmaWxsOiNhZWNiZmE7fSYjeGE7CS5zdDJ7ZmlsbDojNDI4NWY0O30mI3hhOzwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTk2LjE5OSAxNzMuODAxdjI1Ljk5bDE5LjE4MSA4Ljc0di0yNS45MjZ6bTQuNzcxIDguNjYybDkuNjczIDQuNDA4djEyLjk4NWwtOS42NzMtNC4zNzV6bS00Ljc3MS0zOC45Njl2MjEuNjg2bDE5LjE4MSA4LjczMnYtMjEuNjg0bC00LjczNy0yLjA5NXYxNS4wNmwtOS42NzMtNC4zOTV2LTE1LjE3ek02Ny4zNDggMTMwLjMydjU2LjU1bDE5LjExNCA4Ljc4M3YtNTYuNjU4bC00LjczNC0yLjEyN3Y0OS45MDhsLTkuNTUzLTQuMzgxVjEzMi40OXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNOTYuMTE2IDExNy4zMTZsMTkuMjY0LTguNjI4IDQ3LjgwNiAyMS43NjMtMTguNzkgOC42MzJ6bTE5LjI2NCAzNC45MTJsLTE5LjE4MS04Ljc0NiAxOS4xODEtOC43MzkgMTkuMjE1IDguNzU5ek04Ni40NjIgMTM5LjA2bC0xOS4xMTQtOC43NDYgMTkuMTE0LTguNzM5IDE5LjM2MiA4Ljc1OXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMTQ0LjM5NiAxNjAuNjEzdi0yMS41M2wxOC43OS04LjYzMnYyMS42NTd6TTExNS4zOCAxODIuNTNsNDcuODA2LTIxLjcxMnYyNS45MDRsLTQ3LjgwNiAyMS42MjZ6bTAtOC42MTh2LTIxLjY4NGwxOS4yMTUtOC43MzJ2MjEuNTQ1eiIvPiYjeGE7PC9zdmc+',
        'ai platform': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE3LjUiIGZpbGwtcnVsZT0iZXZlbm9kZCIgdmlld0JveD0iMCAwIDIwIDE3LjUiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xOC45MSAxMC42M0wyMCA4Ljc1IDE3LjgyIDVoLTMuMDdsLTEuMDYtMS44NkgxMi41VjEuODhoMS45NGwxLjA2IDEuODdoMS41OUwxNC45IDBoLTQuMjd2NWgxLjczbC43MyAxLjI1aC0yLjQ2djIuNWgyLjI2bDEuMDUtMS44N2gyLjgxbC43MiAxLjI1aC0yLjhMMTMuNjIgMTBoLTIuOTl2NC4zOGgzLjRsLS43MiAxLjI1aC0yLjY4djEuODdoNC4yN2wzLjI4LTUuNjJoLTIuMDlsLS43MyAxLjI1SDEyLjV2LTEuMjVoMi4xNGwuNzQtMS4yNXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMS4wOSAxMC42M0wwIDguNzUgMi4xOCA1aDMuMDdsMS4wNi0xLjg2SDcuNVYxLjg4SDUuNTZMNC41IDMuNzVIMi45MUw1LjEgMGg0LjI4djVINy42NGwtLjczIDEuMjVoMi40N3YyLjVINy4xMUw2LjA2IDYuODhIMy4yNWwtLjcyIDEuMjVoMi44TDYuMzggMTBoM3Y0LjM4SDUuOTdsLjcyIDEuMjVoMi42OXYxLjg3SDUuMWwtMy4yOC01LjYyaDIuMDlsLjczIDEuMjVINy41di0xLjI1SDUuMzZsLS43NC0xLjI1eiIvPiYjeGE7PC9zdmc+',
        'alloydb': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc4NzUzMSIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSIwIDAgMjg0LjM1MTYyIDMwMi42MTMwNyIgaGVpZ2h0PSIzMDIuNjEzMDdtbSIgd2lkdGg9IjI4NC4zNTE2Mm1tIj4mI3hhOyAgJiN4YTsgIDxkZWZzIGlkPSJkZWZzODc1MjgiLz4mI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoMzUuNzQwNDUzLDMuMDI1MTM4NCkiIGlkPSJsYXllcjEiPiYjeGE7ICAgIDxwYXRoIGQ9Ik0gNDAxLjQ3ODUyLC0xMS40MzM1OTQgLTEzMC4xMjEwOSwyNTYuODMwMDggLTU0Ljg4NjcxOSwzMDMuNTM3MTEgNDAxLjUzMTI1LDczLjIwNzAzMSA4MzUuMjEyODksMjkxLjM4NjcyIDkyMy43MTQ4NCwyNTEuMjk0OTIgWiBNIC0xMzUuMDgyMDMsMzQyLjcxNjggdiA1MjcuMzA0NjggbCAyMS40Mjk2OSwxMC4yOTEwMiA1MjQuNzA1MDcsMjUxLjk4ODMgNTI4LjU4MDA4LC0yNjIuNjMyODMgViAzNjguNTY2NDEgbCAtNzUuNTg5ODQsMzQuMjQwMjMgViA4MjIuODIyMjcgTCA0MTAuNDg0MzgsMTA0OC4xNjk5IC01OS40OTAyMzQsODIyLjQ3NDYxIFYgMzg5LjY0NjQ4IFogbSAxNTIuODc4OTA1LDk0LjkxMjExIHYgMzEzLjYyOTQxIGwgNzUuNTkxNzk3LDM3LjEyNjE0IFYgNDg0LjU1ODU5IFogbSA3NTAuNDI5Njg1LDguNTgyMDMgLTc1LjU5MTc5LDM0LjI0MjE4IHYgMzIyLjU1MzYzIGwgNzUuNTkxNzksLTQ3Ljg3MTU1IHoiIHRyYW5zZm9ybT0ic2NhbGUoMC4yNjQ1ODMzMykiIHN0eWxlPSJjb2xvcjojMDAwMDAwO29wYWNpdHk6MTtmaWxsOiM1OTg2ZjI7ZmlsbC1vcGFjaXR5OjE7c3Ryb2tlLXdpZHRoOjMuNzc5NTM7LWlua3NjYXBlLXN0cm9rZTpub25lIiBpZD0icGF0aDExMzIiLz4mI3hhOyAgICA8cGF0aCBpZD0icGF0aDExMzQiIGQ9Im0gMTU2LjQ1ODQsMTY4Ljc2NTA2IC00OS42MTUyNCwyNi43NzIwNSAtNTUuMzkyMzE0LC0yNS4yNjA4OCB2IDIxLjkxNTk2IGwgNTUuMzkyMzE0LDI1Ljc1NTA4IDQ5LjYxNTI0LC0yNy4wMTY3MSB6IiBzdHlsZT0iY29sb3I6IzAwMDAwMDtvcGFjaXR5OjE7ZmlsbDojNzY5ZWY1O2ZpbGwtb3BhY2l0eToxOy1pbmtzY2FwZS1zdHJva2U6bm9uZSIvPiYjeGE7ICAgIDxwYXRoIGQ9Ik0gNTEuNDUwODQ2LDEyMi44MzQyMiAxMDYuODQzMTYsOTMuNTg1NjE0IDE1Ni40NTg0LDEyMi44MzQyMiB2IDIwLjQ3ODYyIEwgMTA2Ljg0MzE2LDE3MC42NDY3MSA1MS40NTA4NDYsMTQzLjMxMjg0IFogTSAxMDUuNDkwMiw0NC4xNTgwMjYgMTAuMjA2MDk1LDk1LjY2MzQxIDI5Ljc4MjE2MSwxMDcuODE2NjcgMTA1LjMzNTY5LDY2Ljk3Njc4OCAxNjcuMTU2MiwxMDEuNDc5MDggMTg5LjgwNzAyLDkxLjIxODIwNCBaIiBzdHlsZT0ib3BhY2l0eToxO2ZpbGw6I2I1Y2JmOTtmaWxsLW9wYWNpdHk6MTtzdHJva2U6bm9uZTtzdHJva2Utd2lkdGg6MjA7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLW9wYWNpdHk6MSIgaWQ9InBhdGgxMTM2Ii8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'analytics hub': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc4MjciIHZlcnNpb249IjEuMSIgdmlld0JveD0iMCAwLjAwMDAwMzgxNDY5NzI2NTYyNSA0ODUuMTE3MzA5NTcwMzEyNSAzNjcuNzkxNDczMzg4NjcxOSIgaGVpZ2h0PSIzNjcuNzkxNDczMzg4NjcxOSIgd2lkdGg9IjQ4NS4xMTczMDk1NzAzMTI1Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgkuc3Qwe2ZpbGw6I2I1Y2JmOTt9CS5zdDF7ZmlsbDojNzY5ZWY1O30JLnN0MntmaWxsOiM1OTg2ZjI7fQk8L3N0eWxlPgkmI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoMTMzLjcyMDcsMzAuMjkzMjQxKSIgaWQ9ImxheWVyMSI+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MCIgZD0ibSAzNy41ODk4NDQsLTE4LjUgYyAtOTQuMzkyMzI1LDJlLTYgLTE3MS4zMTA1NDQsNzYuOTE2MjY5IC0xNzEuMzEwNTQ0LDE3MS4zMDg1OSAwLDk0LjM5MjMyIDc2LjkxODIyMywxNzEuMzEwNTUgMTcxLjMxMDU0NCwxNzEuMzEwNTUgOTQuMzkyMzE2LDAgMTcxLjMwODU4NiwtNzYuOTE4MjMgMTcxLjMwODU5NiwtMTcxLjMxMDU1IDAsLTk0LjM5MjMyMSAtNzYuOTE2MjcsLTE3MS4zMDg1ODYgLTE3MS4zMDg1OTYsLTE3MS4zMDg1OSB6IG0gMCwzNyBjIDc0LjM5NjA1NiwzZS02IDEzNC4zMDg1OTYsNTkuOTEyNTMzIDEzNC4zMDg1OTYsMTM0LjMwODU5IC0xZS01LDc0LjM5NjA2IC01OS45MTI1NCwxMzQuMzEwNTUgLTEzNC4zMDg1OTYsMTM0LjMxMDU1IC03NC4zOTYwNTgsMCAtMTM0LjMxMDU0MiwtNTkuOTE0NDkgLTEzNC4zMTA1NDcsLTEzNC4zMTA1NSAwLC03NC4zOTYwNTcgNTkuOTE0NDg2LC0xMzQuMzA4NTg4IDEzNC4zMTA1NDcsLTEzNC4zMDg1OSB6Ii8+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MSIgdHJhbnNmb3JtPSJzY2FsZSgwLjI2NDU4MzMzKSIgZD0ibSAtMTA2LjU1MDc4LDIzMS42NzM4MyBjIC03Mi44NzcwNCwwIC0xMzIuNzY5NTMsNTkuODkyNDkgLTEzMi43Njk1MywxMzIuNzY5NTMgLTFlLTUsNzIuODc3MDMgNTkuODkyNDksMTMyLjc2MzY3IDEzMi43Njk1MywxMzIuNzYzNjcgMzIuNzk5NjI0LDAgNjIuOTY1MDg1LC0xMi4xMzUxMiA4Ni4yMjY1NjEsLTMyLjEyMTA5IEwgNzAuNjY2MDE2LDUxNy42MjUgMTA4LjQ2Mjg5LDQ1Mi4xNjIxMSAyMC44NTkzNzUsNDAxLjU4MDA4IGMgMy40Nzc4NDEsLTExLjgwMjYyIDUuMzUzNTE2LC0yNC4yNjUyNiA1LjM1MzUxNiwtMzcuMTM2NzIgMCwtNzIuODc3MDQgLTU5Ljg4NjYyOSwtMTMyLjc2OTUzIC0xMzIuNzYzNjcxLC0xMzIuNzY5NTMgeiBtIDAsNzUuNTg5ODQgYyAzMi4wMjQ5MTUsMCA1Ny4xNzM4MjcsMjUuMTU0NzcgNTcuMTczODI3LDU3LjE3OTY5IDAsMzIuMDI0OTIgLTI1LjE0ODkwOSw1Ny4xNzM4MyAtNTcuMTczODI3LDU3LjE3MzgzIC0zMi4wMjQ5MiwwIC01Ny4xNzk2OSwtMjUuMTQ4OTEgLTU3LjE3OTY5LC01Ny4xNzM4MyAwLC0zMi4wMjQ5MiAyNS4xNTQ3NywtNTcuMTc5NjkgNTcuMTc5NjksLTU3LjE3OTY5IHoiLz4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QyIiB0cmFuc2Zvcm09InNjYWxlKDAuMjY0NTgzMzMpIiBkPSJtIDExNDUuODI4MSwtMTE0LjQ5NDE0IGEgMTgwLjQxMTU4LDE4MC40MTE1OCAwIDAgMCAtMTgwLjQxMDEzLDE4MC40MTIxMDkgMTgwLjQxMTU4LDE4MC40MTE1OCAwIDAgMCAyLjAxMTcyLDI2Ljg3NSBMIDQyMS4xNjIxMSw0MDAuNjU2MjUgQSAyMzcuNjU4MzMsMjM3LjY1ODMzIDAgMCAwIDI2NS45ODQzOCwzNDIuOTc2NTYgMjM3LjY1ODMzLDIzNy42NTgzMyAwIDAgMCAyOC4zMjYxNzIsNTgwLjYzNDc3IDIzNy42NTgzMywyMzcuNjU4MzMgMCAwIDAgMjY1Ljk4NDM4LDgxOC4yOTQ5MiAyMzcuNjU4MzMsMjM3LjY1ODMzIDAgMCAwIDQxNy42NTAzOSw3NjMuNDQzMzYgbCA1NTMuMTU4MiwzMTEuNDM3NTQgYSAxNzkuMzUxNzYsMTc5LjM1MTc2IDAgMCAwIC0xLjM5ODQzLDIxLjM0OTYgMTc5LjM1MTc2LDE3OS4zNTE3NiAwIDAgMCAxNzkuMzUxNTQsMTc5LjM1MzUgMTc5LjM1MTc2LDE3OS4zNTE3NiAwIDAgMCAxNzkuMzUxNiwtMTc5LjM1MzUgMTc5LjM1MTc2LDE3OS4zNTE3NiAwIDAgMCAtMTc5LjM1MTYsLTE3OS4zNTE1OSAxNzkuMzUxNzYsMTc5LjM1MTc2IDAgMCAwIC0xMDguNDU5LDM2LjY0NDUzIEwgNDk0LjMwNjY0LDY0Ni4xMjMwNSBBIDIzNy42NTgzMywyMzcuNjU4MzMgMCAwIDAgNTAzLjY0MjU4LDU4MC42MzQ3NyAyMzcuNjU4MzMsMjM3LjY1ODMzIDAgMCAwIDQ5NS41NjgzNiw1MTkuMjUgTCAxMDQwLjQxNDEsMjEyLjE4NTU1IGEgMTgwLjQxMTU4LDE4MC40MTE1OCAwIDAgMCAxMDUuNDE0LDM0LjE0NDUzIDE4MC40MTE1OCwxODAuNDExNTggMCAwIDAgMTgwLjQxMjEsLTE4MC40MTIxMTEgMTgwLjQxMTU4LDE4MC40MTE1OCAwIDAgMCAtMTgwLjQxMjEsLTE4MC40MTIxMDkgeiIvPiYjeGE7ICA8L2c+JiN4YTs8L3N2Zz4=',
        'anthos clusters': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjQwMi4zNDMyMDA2ODM1OTM3NSIgaGVpZ2h0PSI0MTYuMDAyNTMyOTU4OTg0NCIgdmlld0JveD0iMCAwLjAwMDQ5OTk2Mzc2MDM3NTk3NjYgNDAyLjM0MzIwMDY4MzU5Mzc1IDQxNi4wMDI1MzI5NTg5ODQ0Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qxe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MntmaWxsOiNhZWNiZmE7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTM2Ni4xNyA5Mi4wMDNjLTE5LjA1IDAtMzYgMTYuODItMzYgMzUuNzYgMCAxMi42MiA4LjQ2IDI1LjI0IDE5LjA1IDMxLjU1djE0Ny4zbC0xMTAuMDUgNjUuMjEgMTYuOTMgMjcuMzUgMTE4LjUxLTY5LjQyYzQuMjQtMi4xIDguNDctOC40MSA4LjQ3LTE0Ljczdi0xNTUuNjdjMTIuNzEtNi4zNSAxOS4wOS0xOC45MyAxOS4wOS0zMS41NSAyLjA4LTE4Ljk0LTE0Ljg1LTM1LjgtMzYtMzUuOHptLTM4LjExLTIzLjFMMjA5LjU1IDEuNTgzYy00LjI0LTIuMTEtMTAuNTktMi4xMS0xNi45MyAwTDU3LjE3IDc5LjQxM0EzNiAzNiAwIDAgMCAzNiA3My4xMDNjLTE5IDAtMzYgMTYuODMtMzYgMzUuNzZzMTYuOTMgMzUuNzcgMzYgMzUuNzcgMzYtMTYuODMgMzYtMzUuNzdsMTI5LjEtNzMuNjIgMTEwIDYzLjExem0tMTQzLjg5IDI3Ny42OHEtOS41MyAwLTE5IDYuMzFsLTExMC02My4xMXYtMTI2LjIyaC0zNHYxMzQuNjNjMCA2LjMyIDQuMjMgMTIuNjMgOC40NiAxNC43M2wxMTguNTQgNjUuMjF2Mi4xMWMwIDE4LjkzIDE2LjkzIDM1Ljc2IDM2IDM1Ljc2czM2LTE2LjgzIDM2LTM1Ljc2LTE3LTMzLjY2LTM2LTMzLjY2eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik05Ny4zOCAxMzYuMjEzbDEwNS44MiA1OC45MSAxMDMuNy01OC45MS0xMDMuNy02MXptLTYuMzUgNjcuMzJsMTEyLjE3IDYzLjExdi01MC40OWwtMTEyLjE3LTY1LjIxem0wIDYzLjExbDExMi4xNyA2NS4yMXYtNDQuMTdsLTExMi4xNy02NS4yMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMjAzLjE3IDIxNi4xMjN2NTAuNTZsMTEyLjE2LTY1LjI5di01MC4zOXptOTItMjBhOC4xNiA4LjE2IDAgMSAxIDguMTYtOC4xNiA4LjE5IDguMTkgMCAwIDEtOC4xNiA4LjE2em0tOTIgOTEuNTJ2NDQuMTZsMTEyLjE2LTY1LjEydi00NC4xNnptOTItMjIuODhhOC4xNiA4LjE2IDAgMSAxIDguMTYtOC4xNiA4LjE5IDguMTkgMCAwIDEtOC4xNiA4LjE2eiIvPiYjeGE7PC9zdmc+',
        'api analytics': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwLjAxMDAwMDIyODg4MTgzNiIgaGVpZ2h0PSI5LjQ5NDcyOTA0MjA1MzIyMyIgdmlld0JveD0iMC4wMDAyMDYzODQ1NjA0NDI1Mjk2MiAwIDIwLjAxMDAwMDIyODg4MTgzNiA5LjQ5NDcyOTA0MjA1MzIyMyI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDJ7ZmlsbDojYWVjYmZhO30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xLjQ3NiA4LjQzYTQuMzEgNC4zMSAwIDEgMSA2LjA3LS40IDMuNjggMy42OCAwIDAgMS0uMzkuNCA0LjMyIDQuMzIgMCAwIDEtNS42OCAwem01LjItNS4yYTMuMDcgMy4wNyAwIDEgMC0uNCA0LjMzIDMgMyAwIDAgMCAuNC0uNCAzLjA3IDMuMDcgMCAwIDAgMC0zLjkzem02LjE5IDUuMmE0LjMxIDQuMzEgMCAxIDEgNi4wNy0uNCAzLjc4IDMuNzggMCAwIDEtLjQuNCA0LjMxIDQuMzEgMCAwIDEtNS42NyAwem01LjItNS4yYTMuMDcgMy4wNyAwIDEgMC0uNCA0LjMzIDMgMyAwIDAgMCAuNC0uNCAzLjA4IDMuMDggMCAwIDAgMC0zLjkzeiIvPiYjeGE7CTxnIGNsYXNzPSJzdDEiPiYjeGE7CQk8Y2lyY2xlIGN4PSI0LjMxNiIgY3k9IjUuMTkiIHI9IjEuNjkiLz4mI3hhOwkJPGNpcmNsZSBjeD0iMTUuNjk2IiBjeT0iNS4xOSIgcj0iMS42OSIvPiYjeGE7CTwvZz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMTIuMzk2LjU2YS4zMS4zMSAwIDAgMC0uMTgtLjU2aC00LjQyYS4zMS4zMSAwIDAgMC0uMTguNTYgNS43MyA1LjczIDAgMCAxIDIuMTMgMi45Mi4yOC4yOCAwIDAgMCAuMzYuMTYuMjkuMjkgMCAwIDAgLjE3LS4xNyA1LjY3IDUuNjcgMCAwIDEgMi4xMi0yLjkxeiIvPiYjeGE7PC9zdmc+',
        'api monetization': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE4LjMwMDAwMTE0NDQwOTE4IiBoZWlnaHQ9IjE5LjgyNjUwNTY2MTAxMDc0MiIgdmlld0JveD0iLTguNzkxNTE5NjkwMDIxMjMyZS04IDAgMTguMzAwMDAxMTQ0NDA5MTggMTkuODI2NTA1NjYxMDEwNzQyIj4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0fSYjeGE7CS5zdDF7ZmlsbDojYWVjYmZhfSYjeGE7CS5zdDJ7ZmlsbDojNjY5ZGY2fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTMuMDEgMTguNDlhMS41MSAxLjUxIDAgMCAxLTMgMGgwdi00LjI4YTEuNTEgMS41MSAwIDEgMSAzIDB6bTUuMTMgMGExLjUxIDEuNTEgMCAwIDEtMyAwaDB2LTQuMjhhMS41MSAxLjUxIDAgMCAxIDMgMHptNS4wNiAwYTEuNTEgMS41MSAwIDAgMS0zIDB2LTQuMjhhMS41MSAxLjUxIDAgMCAxIDMgMHptNS4wOSAwYTEuNTEgMS41MSAwIDAgMS0zIDB2LTQuMjhhMS41MSAxLjUxIDAgMSAxIDMgMHoiLz4mI3hhOwk8Y2lyY2xlIGNsYXNzPSJzdDEiIGN4PSI2LjU5IiBjeT0iOS45NyIgcj0iMS41MSIvPiYjeGE7CTxjaXJjbGUgY2xhc3M9InN0MiIgY3g9IjExLjY5IiBjeT0iOS45NyIgcj0iMS41MSIvPiYjeGE7CTxjaXJjbGUgY2xhc3M9InN0MSIgY3g9IjExLjY5IiBjeT0iNS43NCIgcj0iMS41MSIvPiYjeGE7CTxnIGNsYXNzPSJzdDIiPiYjeGE7CQk8Y2lyY2xlIGN4PSIxNi43OCIgY3k9IjkuOTciIHI9IjEuNTEiLz4mI3hhOwkJPGNpcmNsZSBjeD0iMTYuNzgiIGN5PSI1Ljc0IiByPSIxLjUxIi8+JiN4YTsJPC9nPiYjeGE7CTxjaXJjbGUgY2xhc3M9InN0MSIgY3g9IjE2Ljc4IiBjeT0iMS41MSIgcj0iMS41MSIvPiYjeGE7PC9zdmc+',
        'apigee api management': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwLjE4MDIzMTA5NDM2MDM1IiBoZWlnaHQ9IjIwLjE4MDIwODIwNjE3Njc1OCIgdmlld0JveD0iLTAuMDAwMTE1MTY1MTIzMTMzOTIwMTMgLTAuMDAwMTAzMzQ0NDkzMjU0NTUzNTMgMjAuMTgwMjMxMDk0MzYwMzUgMjAuMTgwMjA4MjA2MTc2NzU4Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNjY5ZGY2O2ZpbGwtcnVsZTpldmVub2RkfSYjeGE7CS5zdDF7ZmlsbC1ydWxlOmV2ZW5vZGQ7ZmlsbDojNDI4NWY0fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTMuMjkgMTAuMDlsMS4zMi0xLjMyLTEuNzktMS43OWEyLjk0IDIuOTQgMCAwIDEgMi4wOC01IDIuOTIgMi45MiAwIDAgMSAyLjA3Ljg2bDEuOCAxLjc5IDEuMzItMS4zNEw4LjMgMS41YTQuODEgNC44MSAwIDEgMC02LjggNi44em0xMy42IDBsLTEuMzIgMS4zMiAxLjc5IDEuOGEyLjk0IDIuOTQgMCAwIDEtNC4xNiA0LjE1bC0xLjc5LTEuNzktMS4zMiAxLjMyIDEuNzkgMS43OWE0LjgxIDQuODEgMCAxIDAgNi44LTYuOHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNNi45OCAxNy4zNmEyLjk0IDIuOTQgMCAxIDEtNC4xNi00LjE2bDEuNzktMS43OSA0LjE2IDQuMTZ6bTYuMjMtMTQuNTRhMi45MyAyLjkzIDAgMCAxIDUgMi4wOCAzIDMgMCAwIDEtLjg2IDIuMDhsLTEuNzkgMS43OS00LjE1LTQuMTZ6bS0zLjEyIDEwLjQ2YTMuMiAzLjIgMCAwIDEtMy4xOS0zLjE5aDBhMy4yMSAzLjIxIDAgMCAxIDMuMTktMy4xOWgwYTMuMjEgMy4yMSAwIDAgMSAzLjE5IDMuMTloMGEzLjIgMy4yIDAgMCAxLTMuMTkgMy4xOXptNi44LTMuMTlsMS43OS0xLjc5QTQuODEgNC44MSAwIDAgMCAxNi41NzQuMTUzIDQuODEgNC44MSAwIDAgMCAxMS44OCAxLjVsLTEuNzkgMS43OS02LjggNi44LTEuNzkgMS43OWE0LjgxIDQuODEgMCAwIDAgMi4xMDYgOC4xNDdBNC44MSA0LjgxIDAgMCAwIDguMyAxOC42OGwxLjc5LTEuNzl6Ii8+JiN4YTs8L3N2Zz4=',
        'apigee api platform': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwLjE4MDIzMTA5NDM2MDM1IiBoZWlnaHQ9IjIwLjE4MDIwODIwNjE3Njc1OCIgdmlld0JveD0iLTAuMDAwMTE1MTY1MTIzMTMzOTIwMTMgLTAuMDAwMTAzMzQ0NDkzMjU0NTUzNTMgMjAuMTgwMjMxMDk0MzYwMzUgMjAuMTgwMjA4MjA2MTc2NzU4Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNjY5ZGY2O2ZpbGwtcnVsZTpldmVub2RkfSYjeGE7CS5zdDF7ZmlsbC1ydWxlOmV2ZW5vZGQ7ZmlsbDojNDI4NWY0fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTMuMjkgMTAuMDlsMS4zMi0xLjMyLTEuNzktMS43OWEyLjk0IDIuOTQgMCAwIDEgMi4wOC01IDIuOTIgMi45MiAwIDAgMSAyLjA3Ljg2bDEuOCAxLjc5IDEuMzItMS4zNEw4LjMgMS41YTQuODEgNC44MSAwIDEgMC02LjggNi44em0xMy42IDBsLTEuMzIgMS4zMiAxLjc5IDEuOGEyLjk0IDIuOTQgMCAwIDEtNC4xNiA0LjE1bC0xLjc5LTEuNzktMS4zMiAxLjMyIDEuNzkgMS43OWE0LjgxIDQuODEgMCAxIDAgNi44LTYuOHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNNi45OCAxNy4zNmEyLjk0IDIuOTQgMCAxIDEtNC4xNi00LjE2bDEuNzktMS43OSA0LjE2IDQuMTZ6bTYuMjMtMTQuNTRhMi45MyAyLjkzIDAgMCAxIDUgMi4wOCAzIDMgMCAwIDEtLjg2IDIuMDhsLTEuNzkgMS43OS00LjE1LTQuMTZ6bS0zLjEyIDEwLjQ2YTMuMiAzLjIgMCAwIDEtMy4xOS0zLjE5aDBhMy4yMSAzLjIxIDAgMCAxIDMuMTktMy4xOWgwYTMuMjEgMy4yMSAwIDAgMSAzLjE5IDMuMTloMGEzLjIgMy4yIDAgMCAxLTMuMTkgMy4xOXptNi44LTMuMTlsMS43OS0xLjc5QTQuODEgNC44MSAwIDAgMCAxNi41NzQuMTUzIDQuODEgNC44MSAwIDAgMCAxMS44OCAxLjVsLTEuNzkgMS43OS02LjggNi44LTEuNzkgMS43OWE0LjgxIDQuODEgMCAwIDAgMi4xMDYgOC4xNDdBNC44MSA0LjgxIDAgMCAwIDguMyAxOC42OGwxLjc5LTEuNzl6Ii8+JiN4YTs8L3N2Zz4=',
        'apigee sense': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwLjAwMDMyOTk3MTMxMzQ3NyIgaGVpZ2h0PSIyMC4wMDAxNjQwMzE5ODI0MjIiIHZpZXdCb3g9Ii0wLjAwMDE2NDgyMzAwOTk4MTc3MzggLTAuMDAwMTY0ODgzMTA5MzkxNjY2OTUgMjAuMDAwMzI5OTcxMzEzNDc3IDIwLjAwMDE2NDAzMTk4MjQyMiI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNH0mI3hhOwkuc3Qxe2ZpbGw6IzY2OWRmNn0mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYX0mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xOS40MiA3bC0uMzUtLjA5TDE4IDYuNjRsLS4wOS0uMTljLS4wNS0uMDktLjA5LS4xOS0uMTQtLjI5bC0uMTQtLjI3LS4xNi0uMjgtLjE2LS4yNi0uMTctLjI2YTIuMzUgMi4zNSAwIDAgMC0uMTktLjI1bC0uMTktLjI1LS4yLS4yNC0uMi0uMjMtLjI2LS4yMi0uMjItLjIyLS4yNC0uMi0uMjMtLjItLjI1LS4xOS0uMjUtLjE5LS4yNi0uMTctLjI2LS4xNi0uMjgtLjE2LS4yNy0uMTQtLjI5LS4xNC0uMTktLjA4LS4yOS0xLjEyTDEzIC41OGEuNzguNzggMCAwIDAtLjc3LS41OEg3Ljc3QS43OC43OCAwIDAgMCA3IC41OGwtLjA5LjM1LS4yNyAxLjEyLS4xOS4wOC0uMjkuMTQtLjI3LjE0LS4yOC4xNi0uMjYuMTYtLjI2LjE3LS4yNS4xOS0uMjUuMTktLjI0LjItLjIzLjItLjIyLjIyLS4yMi4yMi0uMi4yNGEyLjIgMi4yIDAgMCAwLS4yLjIzYy0uMDcuMDgtLjEzLjE3LS4xOS4yNWEyLjM1IDIuMzUgMCAwIDAtLjE5LjI1bC0uMTcuMjYtLjE2LjI2LS4xNi4yOGMwIC4wOS0uMS4xOC0uMTQuMjdsLS4xNC4yOWMtLjA1LjA5LS4wNi4xMy0uMDguMTlsLTEuMTIuMjlMLjU4IDdhLjc4Ljc4IDAgMCAwLS41OC43N3Y0LjQ2YS43OC43OCAwIDAgMCAuNTguNzVsLjM1LjA5IDEuMTIuMjljMCAuMDYuMDYuMTIuMDguMTlzLjA5LjE5LjE0LjI5bC4xNC4yNy4xNi4yOC4xNi4yNi4xNy4yNmEyLjM1IDIuMzUgMCAwIDAgLjE5LjI1bC4xOS4yNWEyLjIgMi4yIDAgMCAwIC4yLjIzbC4yLjI0LjIyLjIyLjIyLjIyLjI0LjIuMjMuMi4yNS4xOS4yNS4xOS4yNi4xNy4yNi4xNi4yOC4xNi4yNy4xNC4yOS4xNC4xOS4wOC4yOSAxLjEyLjA5LjM1YS43OC43OCAwIDAgMCAuNzUuNThoNC40NmEuNzguNzggMCAwIDAgLjc1LS41OGwuMDktLjM1LjI5LTEuMDcuMTktLjA4LjI5LS4xNC4yNy0uMTQuMjgtLjE2LjI2LS4xNi4yNi0uMTcuMjUtLjE5LjI1LS4xOS4yNC0uMi4yMy0uMi4yMi0uMjIuMjItLjIyLjItLjI0YTIuMiAyLjIgMCAwIDAgLjItLjIzYy4wNy0uMDguMTMtLjE3LjE5LS4yNWEyLjM1IDIuMzUgMCAwIDAgLjE5LS4yNWwuMTctLjI2LjE2LS4yNi4xNi0uMjguMTQtLjI3LjE0LS4yOWMuMDUtLjA5LjA2LS4xMy4wOC0uMTlsMS4xMi0uMjkuMzUtLjA5YS43OC43OCAwIDAgMCAuNTgtLjc1VjcuNzdhLjc4Ljc4IDAgMCAwLS41OC0uNzd6TTEwIDE2LjY3QTYuNjYgNi42NiAwIDEgMSAxNi42NyAxMGE2LjUzIDYuNTMgMCAwIDEtLjE0IDEuMzNBNi42NCA2LjY0IDAgMCAxIDEwIDE2LjY3eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xMCA0Ljg4QTUuMTcgNS4xNyAwIDAgMCA4Ljg5IDVsLjI3IDEuMjNhMy44NiAzLjg2IDAgMSAxLTIuOTMgNC42MSA0IDQgMCAwIDEtLjA5LS44NEg0Ljg4QTUuMTIgNS4xMiAwIDEgMCAxMCA0Ljg4eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0xMCA3LjQyYTIuNiAyLjYgMCAwIDAtLjU2LjA2bC4yNyAxLjI0YTEuMzIgMS4zMiAwIDEgMS0xIDEuNTcgMS40MyAxLjQzIDAgMCAxIDAtLjI5SDcuNDJBMi41OCAyLjU4IDAgMSAwIDEwIDcuNDJ6Ii8+JiN4YTs8L3N2Zz4=',
        'app engine': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE2LjAyMDAwMDQ1Nzc2MzY3MiIgZmlsbC1ydWxlPSJldmVub2RkIiB2aWV3Qm94PSI4Ljk0MDY5NjcxNjMwODU5NGUtOCAwIDIwIDE2LjAyMDAwMDQ1Nzc2MzY3MiI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiNhZWNiZmE7fSYjeGE7CS5zdDJ7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xMi4zIDcuMjZsLTEuMjIgMS4yMkExLjcxIDEuNzEgMCAwIDEgMTAgMTEuNDlhMS43NCAxLjc0IDAgMCAxLTEuMzMtLjY0bC0xLjIyIDEuMjJhMy40MyAzLjQzIDAgMCAwIDUuOTg0LTEuMzgxQTMuNDMgMy40MyAwIDAgMCAxMi4zIDcuMjZ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwIDMuNTJhNi4yNSA2LjI1IDAgMCAwIDAgMTIuNSA2LjI1IDYuMjUgMCAwIDAgMC0xMi41bTAgMTAuNzRhNC40NSA0LjQ1IDAgMCAxLTMuMTU3LTcuNTk3QTQuNDUgNC40NSAwIDAgMSAxNC40NCA5LjgyIDQuNDQgNC40NCAwIDAgMSAxMCAxNC4yNiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0xOS42MiA5LjE2bC0yLjU2LS44MWE3LjEgNy4xIDAgMCAxIC4xNyAxLjUzIDcuNjIgNy42MiAwIDAgMS0uMDggMS4wOGgyLjQ3YS40NC40NCAwIDAgMCAuMzgtLjQydi0xYS40NC40NCAwIDAgMC0uMzgtLjQyTTEwIDIuNzhhNy40OCA3LjQ4IDAgMCAxIDEuNS4xNUwxMC41OC4zOGMtLjA3LS4yMi0uMjEtLjM4LS40Mi0uMzhoLS4zOGEuNDUuNDUgMCAwIDAtLjQyLjM4bC0uOCAyLjU0QTcuNjQgNy42NCAwIDAgMSAxMCAyLjc4bS03LjIzIDcuMWE3LjEgNy4xIDAgMCAxIC4xNy0xLjUzbC0yLjU2LjgxYS40NC40NCAwIDAgMC0uMzguNDJ2MWEuNDQuNDQgMCAwIDAgLjM4LjQyaDIuNDdhNy42MiA3LjYyIDAgMCAxLS4wOC0xLjA4Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwIDcuMjZhMi41IDIuNSAwIDEgMCAwIDUgMi41IDIuNSAwIDEgMCAwLTV6bTAgMy43NWExLjI1IDEuMjUgMCAxIDEgMC0yLjUgMS4yNSAxLjI1IDAgMCAxIDEuMjUgMS4yNUExLjI1IDEuMjUgMCAwIDEgMTAgMTEuMDJ6Ii8+JiN4YTs8L3N2Zz4=',
        'automl': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE4IiB2aWV3Qm94PSIwIDAgMjAgMTgiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O2ZpbGwtb3BhY2l0eTouOH0mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTtmaWxsLW9wYWNpdHk6LjZ9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNOS4xNyA1LjE0bDEuNjYtMi41N0w5LjE1IDBINUwwIDguNThsMi41IDUuMTQgNS04LjU4eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xNC4xNyA1LjE0bDEuNjYtMi41N0wxNC4xNyAwaC0zLjM0bDEuNjcgMi41Ny0xLjY3IDIuNTd6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTEwLjgzIDEyLjg2bC0xLjY2IDIuNTdMMTAuODUgMThIMTVsNS04LjU4LTIuNS01LjE0LTUgOC41OHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNOS4xNyAxMi44Nkg1LjgzbC0xLjY2IDIuNTdMNS44MyAxOGgzLjM0TDcuNSAxNS40M3oiLz4mI3hhOzwvc3ZnPg==',
        'automl natural language': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM4MC41MTE5Nzg1NDYzNTQ0NCIgaGVpZ2h0PSIyNzQuOTI5OTg3NzczNzYyNTUiIHZpZXdCb3g9IjAgMCAxMDAuNjc2OTk0MzIzNzMwNDcgNzIuNzQxOTk2NzY1MTM2NzIiPiYjeGE7PHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0zNy41NyA0NC43MjRoMjUuNDc3djUuNDY5SDM3LjU3em0wLTEwLjE0NmgyNS40Nzd2NS40NjlIMzcuNTd6bTAtMTAuMTQ2aDI1LjQ3N3Y1LjQ2OUgzNy41N3ptNTMuNTIgMi4yNzhsOS41ODcgMTMuMTQzLTIzLjc4MiAzMi44ODlIMjkuMDdsLTQuNzQxLTYuNTY4IDQuODExLTYuNTYxaDM4LjEwMXpNOS41ODcgNDYuMDMyTDAgMzIuODg5IDIzLjc4MiAwaDQ3LjgyNWw0Ljc0MSA2LjU2OC00LjgxMSA2LjU2MUgzMy40Mzd6Ii8+JiN4YTs8L3N2Zz4=',
        'automl tables': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM4MC42MzY0OTE2NzUyNjI0NSIgaGVpZ2h0PSIyNzUuNjgyNTM0NzQ5ODYxMTMiIHZpZXdCb3g9Ii0wLjM2OTAwMDAxNzY0Mjk3NDg1IDAgMTAwLjcxMDAwNjcxMzg2NzE5IDcyLjk0MTAwMTg5MjA4OTg0Ij4mI3hhOzxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojYWVjYmZhO30mI3hhOwkuc3Qye2ZpbGw6IzY2OWRmNjt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xMDAuMzQxIDQwLjA4TDc2LjQ0IDcyLjk0MWwtNDcuNjkyLS4wNy00Ljg0Ni02LjY1OSA0Ljg4MS02LjU4OSAzOC4xMDUuMDcgMjMuNzY1LTMyLjg0NXpNLS4zNjkgMzIuODYxTDIzLjUzMiAwbDQ3LjY5Mi4wNyA0Ljg0NiA2LjY1OS00Ljg4MSA2LjU4OS0zOC4xMDUtLjA3TDkuMzE5IDQ2LjA5M3oiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMzYuMjQgNDMuNzUyVjI3LjU3NmwxNy4xMTcgOC4wMTh2MTYuOTc4eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik01OC4wMTEgNDEuNjk1di04LjgybC05Ljk1My00LjYzN3YtNy45ODNsMTcuMTE3IDguMTIzdjE3LjAxM3oiLz4mI3hhOzwvc3ZnPg==',
        'automl translation': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM4MC42MzY0OTE2NzUyNjI0NSIgaGVpZ2h0PSIyNzUuNjgyNTM0NzQ5ODYxMTMiIHZpZXdCb3g9Ii0wLjM2OTAwMDAxNzY0Mjk3NDg1IDAgMTAwLjcxMDAwNjcxMzg2NzE5IDcyLjk0MTAwMTg5MjA4OTg0Ij4mI3hhOzxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xMDAuMzQxIDQwLjA4TDc2LjQ0IDcyLjk0MWwtNDcuNjkyLS4wNy00Ljg0Ni02LjY1OSA0Ljg4MS02LjU4OSAzOC4xMDUuMDcgMjMuNzY1LTMyLjg0NXpNLS4zNjkgMzIuODYxTDIzLjUzMiAwbDQ3LjY5Mi4wNyA0Ljg0NiA2LjY1OS00Ljg4MSA2LjU4OS0zOC4xMDUtLjA3TDkuMzE5IDQ2LjA5M3oiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMzMuOTc0IDI5Ljg3N3YtNC4wNjFoMTIuODk5di00LjYzN2g1LjUyNnY0LjYzN2gxMy4zMTd2NC4wNjF6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTYzLjg2OCA1MS43N2MtNC40NTItLjY4Mi05LjQ4MS0yLjk1NS0xMy43MzYtNS45NjEtNC4wNjUgMi41MzItOC41ODIgNC43NDEtMTMuOTQ1IDYuMzQ1bC0zLjEwMy00LjAwOWM0Ljc2NS0xLjA2MSA5LjIzNy0yLjk5NSAxMy4wNzMtNS41NDMtMi41NDQtMi41NDMtNC43MjktNS4zNTQtNi4zNDUtOC40NTRoNi4xMDFjMS4xNDYgMS45ODcgMi41NjMgMy42NTMgNC4wNzkgNS4xNzcgMS43NTgtMS41OSAzLjAyOC0zLjMwOSA0LjA0NC01LjE3N2g2LjIwNWMtMS40MzIgMi44ODktMy4yMTggNS43MDItNi4zMSA4LjMxNWEzNS43NyAzNS43NyAwIDAgMCAxMi43NiA1LjEyNXoiLz4mI3hhOzwvc3ZnPg==',
        'automl vision': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE4IiB2aWV3Qm94PSIwIDAgMjAgMTgiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O2ZpbGwtcnVsZTpldmVub2RkfSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTE1LjkxIDcuMmgtMS44MkwxMCAxOGgxLjgybDEtMi43aDQuMzJsMSAyLjdIMjB6bS0yLjM5IDYuM0wxNSA5LjZsMS40OCAzLjl6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwLjc5IDExLjc3TDguNDggOS41MWgwYTE1LjYyIDE1LjYyIDAgMCAwIDMuNC01LjkxaDIuNjdWMS44SDguMThWMEg2LjM2djEuOEgwdjEuNzloMTAuMTVhMTQuMDYgMTQuMDYgMCAwIDEtMi44OCA0LjgyIDE0LjU1IDE0LjU1IDAgMCAxLTIuMS0zSDMuMzVhMTYgMTYgMCAwIDAgMi43MSA0LjFMMS40NCAxNGwxLjI5IDEuMyA0LjU0LTQuNSAyLjgzIDIuOHoiLz4mI3hhOzwvc3ZnPg==',
        'bare metal solution': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmcyNzk1MiIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSI3Mi4zNDk0ODczMDQ2ODc1IDE0MC40MjA0MjU0MTUwMzkwNiA2NDMuMzYxMzI4MTI1IDY3OC4xOTg3MzA0Njg3NSIgaGVpZ2h0PSI2NzguMTk4NzMwNDY4NzUiIHdpZHRoPSI2NDMuMzYxMzI4MTI1Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgkuc3Qwe2ZpbGw6IzQyODVmNDt9CTwvc3R5bGU+CSYjeGE7ICA8ZyB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMjYuMDI5NDE5LC01MC41MTk1MykiIGlkPSJsYXllcjEiPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0gNjkxLjM4ODY3LDUzNS4wMDE5NSA0MjAuMzk4NDQsODA2LjY2NDA2IDE0OS40MjM4Myw1MzUuNjg5NDUgMTIzLjc3MTQ4LDU2MS4zNDc2NiAyMTQuNDc4NTIsNjUyLjA1NDY5IDk4LjM3ODkwNiw3MDkuMTgzNTkgNDIxLjgzMDA4LDg2OS4xMzg2NyA3NDEuNzQwMjMsNzA4LjQ3NDYxIDYyNi4wMzkwNiw2NTEuODgyODEgNzE3LjA3MDMxLDU2MC42MjUgWiBNIDQyMC4zOTg2MywxOTAuOTM5OTYgMTM1LjczMDgxLDQ3NS42MDA0MSAxNDguNTIzNjIsNDg4LjQzMDEzIDQyMC4zOTg2Myw3NjEuMDQzMyA3MDUuODQxNTYsNDc1LjYwMDQxIFogbSAwLjAzMDIsNTEuMjc0NjEgTCA2NTQuNDkzODQsNDc1LjYzNzMgNDIwLjQyODg3LDcwOS42OTQ5IDE4Ny4wMTM1Miw0NzUuNjI5OTMgWiIvPiYjeGE7ICA8L2c+JiN4YTs8L3N2Zz4=',
        'beyondcorp': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE4LjgyMzUxNDkzODM1NDQ5MiIgaGVpZ2h0PSIyMC4wNzA1Mzc1NjcxMzg2NzIiIHZpZXdCb3g9IjAuMDAwMDExMzM3Nzc3MzIzMjA1OTU1IDAuMDAwMDg1NjY1MDQ0MDI1NTE4IDE4LjgyMzUxNDkzODM1NDQ5MiAyMC4wNzA1Mzc1NjcxMzg2NzIiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTE2LjkzIDQuOTc2YTEwLjQzIDEwLjQzIDAgMCAxLTEgLjkyIDguMDkgOC4wOSAwIDAgMS0xMC41MSAxMS44MWgxLjc1YTcuNTEgNy41MSAwIDAgMS0uODYtMS4zSDMuNzNhOC43NSA4Ljc1IDAgMCAxLTEtMS4xOWgzLjA2YTEwLjM4IDEwLjM4IDAgMCAxLS4zNy0xLjMxSDIuMDFhOCA4IDAgMCAxLS40Mi0xLjE5aDMuNTdjLS4wNy0uNDItLjExLS44NS0uMTQtMS4zSDEuMzZhNi41MSA2LjUxIDAgMCAxIDAtLjc3di0uNDNoMy42M2ExMS4zNCAxMS4zNCAwIDAgMSAuMDgtMS4zSDEuNWE4LjE2IDguMTYgMCAwIDEgLjM2LTEuMTloMy40YTkuNTIgOS41MiAwIDAgMSAuMzMtMS4zSDIuNTJhOCA4IDAgMCAxIC45LTEuMTloMi42MWE5LjIgOS4yIDAgMCAxIC43MS0xLjMxSDQuOTJhOC4wNiA4LjA2IDAgMCAxIDcuNzQtLjY5IDEwLjcgMTAuNyAwIDAgMCAxLjI5IDMuMTlzMi45My0xLjY3IDMuMzgtMy40NGEyLjQyIDIuNDIgMCAwIDAtNC42OC0xLjIzdi4wN2E5LjQxIDkuNDEgMCAxIDAgNi4xNyA4LjgyIDguNzEgOC43MSAwIDAgMC0xLjg5LTUuNjd6bS0zLjAxLTIuOTJhMS4xNCAxLjE0IDAgMSAxIC44MSAxLjM5aDBhMS4xMyAxLjEzIDAgMCAxLS44MS0xLjM5eiIvPiYjeGE7PC9zdmc+',
        'bigquery': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwLjAwMTA0NTIyNzA1MDc4IiBoZWlnaHQ9IjIwLjAwMTA0NTIyNzA1MDc4IiBmaWxsLXJ1bGU9ImV2ZW5vZGQiIHZpZXdCb3g9IjAgMCAyMC4wMDEwNDUyMjcwNTA3OCAyMC4wMDEwNDUyMjcwNTA3OCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDJ7ZmlsbDojNDI4NWY0O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik00LjczIDguODN2Mi42M2E0LjkxIDQuOTEgMCAwIDAgMS43MSAxLjc0VjguODN6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTcuODkgNi40MXY3LjUzQTcuNjIgNy42MiAwIDAgMCA5IDE0YTggOCAwIDAgMCAxIDBWNi40MXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTEuNjQgOS44NnYzLjI5YTUgNSAwIDAgMCAxLjctMS44MlY5Ljg2eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0xNS43NCAxNC4zMmwtMS40MiAxLjQyYS40Mi40MiAwIDAgMCAwIC42bDMuNTQgMy41NGEuNDIuNDIgMCAwIDAgLjU5IDBsMS40My0xLjQzYS40Mi40MiAwIDAgMCAwLS41OWwtMy41NC0zLjU0YS40Mi40MiAwIDAgMC0uNiAwIi8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTkgMGE5IDkgMCAxIDAgMCAxOEE5IDkgMCAxIDAgOSAwbTAgMTUuNjlhNi42OCA2LjY4IDAgMCAxIC4wMDctMTMuMzYgNi42OCA2LjY4IDAgMCAxIDQuNzI3IDExLjQwM0E2LjY4IDYuNjggMCAwIDEgOSAxNS42OSIvPiYjeGE7PC9zdmc+',
        'chronicle': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc5NjI2MCIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSItMC4wMDAwMDM4MTQ2OTcyNjU2MjUgMCAxMTcuODk1OTUwMzE3MzgyODEgMTUyLjIwNzUxOTUzMTI1IiBoZWlnaHQ9IjE1Mi4yMDc1MTk1MzEyNSIgd2lkdGg9IjExNy44OTU5NTAzMTczODI4MSI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4JLnN0MHtmaWxsOiM0Mjg1ZjQ7fQkuc3Qxe2ZpbGw6IzM0YTg1Mzt9CS5zdDJ7ZmlsbDojZmJiYzA1O30JLnN0M3tmaWxsOiNlYTQzMzU7fQk8L3N0eWxlPgkmI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTQ1LjI3MzMxNywtNzEuNTI1NTk3KSIgaWQ9ImxheWVyMSI+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MCIgZD0iTSA0NS4yNzMzMTcsNzEuNTI1NTk3IEggMTYzLjE2NTA2IFYgMTAxLjg3MzMzIEggNDUuMjczMzE3IFoiLz4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QxIiBkPSJtIDQ1LjI3MzMxNywxNjUuNTIwMjEgdiAtNjMuNjQ2ODggbCAzMC4zOTQxNjgsMTguOTU4NDggdiAyNS41MTQ2NiB6Ii8+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MiIgZD0ibSA1Mi4xMjU0NzYsMTkxLjE2Mzk2IGMgLTQuNzk0MzE4LC0yLjk3MzQgLTYuODUyMTU5LC02LjQ2NDI2IC02Ljg1MjE1OSwtMTEuNTI1MzIgdiAtMTQuMTE4NDMgbCAzMC4zOTQxNjgsLTE5LjE3Mzc0IHYgNTkuNTExMDIgeiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDMiIGQ9Im0gMTYzLjE2NTA2LDE1MS4wOTgyOCB2IDI4LjM0NzAyIGMgMC4xMDUwNCw0Ljk2OTY5IC0xLjc1NTM5LDguMzQxNiAtNS43NzAwNywxMS4wOTUzNiBsIC01My4wNDI0LDMzLjE5MjQ3IC0yOC42ODUxMDUsLTE3Ljg3NTY0IHoiLz4mI3hhOyAgPC9nPiYjeGE7PC9zdmc+',
        'cloud ai': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE3LjUiIGZpbGwtcnVsZT0iZXZlbm9kZCIgdmlld0JveD0iMCAwIDIwIDE3LjUiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xOC45MSAxMC42M0wyMCA4Ljc1IDE3LjgyIDVoLTMuMDdsLTEuMDYtMS44NkgxMi41VjEuODhoMS45NGwxLjA2IDEuODdoMS41OUwxNC45IDBoLTQuMjd2NWgxLjczbC43MyAxLjI1aC0yLjQ2djIuNWgyLjI2bDEuMDUtMS44N2gyLjgxbC43MiAxLjI1aC0yLjhMMTMuNjIgMTBoLTIuOTl2NC4zOGgzLjRsLS43MiAxLjI1aC0yLjY4djEuODdoNC4yN2wzLjI4LTUuNjJoLTIuMDlsLS43MyAxLjI1SDEyLjV2LTEuMjVoMi4xNGwuNzQtMS4yNXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMS4wOSAxMC42M0wwIDguNzUgMi4xOCA1aDMuMDdsMS4wNi0xLjg2SDcuNVYxLjg4SDUuNTZMNC41IDMuNzVIMi45MUw1LjEgMGg0LjI4djVINy42NGwtLjczIDEuMjVoMi40N3YyLjVINy4xMUw2LjA2IDYuODhIMy4yNWwtLjcyIDEuMjVoMi44TDYuMzggMTBoM3Y0LjM4SDUuOTdsLjcyIDEuMjVoMi42OXYxLjg3SDUuMWwtMy4yOC01LjYyaDIuMDlsLjczIDEuMjVINy41di0xLjI1SDUuMzZsLS43NC0xLjI1eiIvPiYjeGE7PC9zdmc+',
        'cloud armor': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE2LjUwMDQzNDg3NTQ4ODI4IiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSItMC4wMDAzNjMwODkyNjA2NDUyMTA3NCAxLjE5MjA5Mjg5NTUwNzgxMjVlLTcgMTYuNTAwNDM0ODc1NDg4MjggMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDF7ZmlsbDojYWVjYmZhO30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xMC40MiAxMi4wN2wxLjA0IDEuMDUtNS40NSA1LjQ4LTEuMDQtMS4wNXptLS44My00LjE5bDEuMDQgMS4wNS03LjM1IDcuMzktMS4wNC0xLjA1em0tNC4xNi0uODVsMS4wNCAxLjA1LTQuODggNC45LTEuMDQtMS4wNXoiLz4mI3hhOwk8ZyBjbGFzcz0ic3QwIj4mI3hhOwkJPHBhdGggZD0iTTguMjUgMS42MWw2Ljc4IDN2NC41NWE5LjcxIDkuNzEgMCAwIDEtNi43OCA5LjMyIDkuNyA5LjcgMCAwIDEtNi43OC05LjMxVjQuNjNsNi43OC0zbTAtMS42M0wwIDMuNjh2NS40OUExMS4xNyAxMS4xNyAwIDAgMCA4LjEgMjBoLjE1LjE1YTExLjE3IDExLjE3IDAgMCAwIDguMS0xMC43OFYzLjY4eiIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIxMC45NCIgY3k9IjEyLjYyIiByPSIxLjQyIi8+JiN4YTsJCTxjaXJjbGUgY3g9IjEwLjEiIGN5PSI4LjQ1IiByPSIxLjQyIi8+JiN4YTsJCTxjaXJjbGUgY3g9IjUuOTQiIGN5PSI3LjYiIHI9IjEuNDIiLz4mI3hhOwk8L2c+JiN4YTs8L3N2Zz4=',
        'cloud bigtable': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE3Ljk1Njk3Nzg0NDIzODI4IiBoZWlnaHQ9IjIwLjAwOTI1NjM2MjkxNTA0IiB2aWV3Qm94PSItMC4wMDA0MjE5NjUxMTY0MDIxMzQzIDAuMDAwMDc0Njk5NTIxMDY0NzU4MyAxNy45NTY5Nzc4NDQyMzgyOCAyMC4wMDkyNTYzNjI5MTUwNCI+JiN4YTsJPHN0eWxlPiYjeGE7CQkuc3Qwe2ZpbGw6IzY2OWRmNjt9JiN4YTsJCS5zdDF7ZmlsbDojYWVjYmZhO30mI3hhOwkJLnN0MntmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPGcgZmlsbC1ydWxlPSJldmVub2RkIj4mI3hhOwkJPHBhdGggZD0iTTEzLjE5NiA0LjQ0N2wtNC4yMi0yLjUxYTIuODYgMi44NiAwIDAgMS0xLjI1LTEuNzFjMCAwIC4xNi0uMzIuMzgtLjJsNS4yNSAzLjFjLjYzLjM3LjI0IDIgLjI0IDJhLjc3Ljc3IDAgMCAwLS40LS42OHoiIGNsYXNzPSJzdDAiLz4mI3hhOwkJPHBhdGggZD0iTTE0LjQ2NiAxMC42ODdhLjM1LjM1IDAgMCAxLS4xNi4zM2wtMSAuNjh2LTcuOTVjMC0uMjcuMTctLjU2LS4wNi0uN2wuOTIuNjhhLjczLjczIDAgMCAxIC4zNS42NXoiIGNsYXNzPSJzdDEiLz4mI3hhOwkJPHBhdGggZD0iTTguOTc2IDExLjU5N2EuMzYuMzYgMCAwIDEtLjItLjA2bC0zLjQ2LTIuMDZ2LjlsMy42NiAyLjE4LjI5LS41N3MtLjIyLS4zOS0uMjktLjM5em0uMiAxLjhhLjM2LjM2IDAgMCAxLS40IDBsLTMuNDYtMi4wNnYuNjZhLjQyLjQyIDAgMCAwIC4xOS4zNWwzLjI4IDJhLjM3LjM3IDAgMCAwIC4zOCAwIDIgMiAwIDAgMCAuMi0uNTJsLS4xOS0uMzl6IiBjbGFzcz0ic3QwIi8+JiN4YTsJCTxwYXRoIGQ9Ik04Ljk3NiAxMC43MjdsMy42Ni0yLjE4di0uNDNhLjM5LjM5IDAgMCAwLS4xOS0uMzRsLTMuMjgtMmEuMzcuMzcgMCAwIDAtLjM4IDBsLTMuMjggMmEuNDEuNDEgMCAwIDAtLjE5LjM0di40M3oiIGNsYXNzPSJzdDEiLz4mI3hhOwkJPHBhdGggZD0iTTguOTc2IDkuODI3bC0zLjQ3LTIuMDVhLjQxLjQxIDAgMCAwLS4xOS4zNHYuNDNsMy42NiAyLjE4LjI4LS41NnoiIGNsYXNzPSJzdDAiLz4mI3hhOwkJPGcgY2xhc3M9InN0MiI+JiN4YTsJCQk8cGF0aCBkPSJNOC45NzYgMTEuNTk3djFsMy42Ni0yLjE4di0uOWwtMy40NiAyLjAyYS42NS42NSAwIDAgMS0uMi4wNnptLjIgMS44YS4zNi4zNiAwIDAgMS0uMi4wNnYuOWEuNS41IDAgMCAwIC4yMS0uMDVsMy4yOC0yYS4zOS4zOSAwIDAgMCAuMTktLjM1di0uNjZ6Ii8+JiN4YTsJCQk8cGF0aCBkPSJNMTIuNDQ2IDcuNzc3bC0zLjQ3IDIuMDV2LjlsMy42Ni0yLjE4di0uNDNhLjM5LjM5IDAgMCAwLS4xOS0uMzR6Ii8+JiN4YTsJCTwvZz4mI3hhOwkJPHBhdGggZD0iTTQuNzU2IDE1LjUyN2w0LjE1IDIuNDdhMi43MiAyLjcyIDAgMCAxIDEuMjggMS44LjE4LjE4IDAgMCAxLS4yOC4xOGwtNS40NS0zLjIzYy0uNTMtLjMyLS4wNy0xLjg4LS4wNy0xLjg4YS43Ny43NyAwIDAgMCAuMzcuNjZ6IiBjbGFzcz0ic3QwIi8+JiN4YTsJCTxwYXRoIGQ9Ik0zLjQ4NiAxNS43Mjd2LTYuNTZhLjQxLjQxIDAgMCAxIC4xOS0uMzNsMS0uNTl2Ny45MWMwIC4yNyAwIC42OS4yMS44M2wtMS4wNi0uNjZhLjc1Ljc1IDAgMCAxLS4zNC0uNnoiIGNsYXNzPSJzdDEiLz4mI3hhOwkJPHBhdGggZD0iTTcuMTM2IDMuNDU3YS43NS43NSAwIDAgMC0uNzQgMGwtNC4yIDIuNTRhMi42MyAyLjYzIDAgMCAxLTIuMDguMjYuMjMuMjMgMCAwIDEgMC0uNGMuMTgtLjA5IDYuMzItMy43NCA2LjMyLTMuNzQuMjMtLjE0Ljc0IDEuMzkuNzQgMS4zOXoiIGNsYXNzPSJzdDAiLz4mI3hhOwkJPHBhdGggZD0iTTcuMTI2IDIuMDc3bDUuMzIgMy4xNWEuMzcuMzcgMCAwIDEgLjIuMzF2MS4xOGwtNi42Ny0zLjk2YS43NS43NSAwIDAgMC0uNzQgMGwxLjE4LS42OWEuNzEuNzEgMCAwIDEgLjczIDB6IiBjbGFzcz0ic3QxIi8+JiN4YTsJCTxwYXRoIGQ9Ik0xMC43OTYgMTYuNDg3YS43My43MyAwIDAgMCAuNzQgMGw0LjItMi40OWEyLjYzIDIuNjMgMCAwIDEgMi4xLS4yNS4yMS4yMSAwIDAgMSAwIC4zOGwtNi4zMyAzLjc1Yy0uMjIuMTQtLjc0LTEuNC0uNzQtMS40eiIgY2xhc3M9InN0MCIvPiYjeGE7CQk8cGF0aCBkPSJNNS40ODYgMTQuNzQ3YS41Ni41NiAwIDAgMS0uMTctLjMzdi0xLjE2bDYuNjYgMy45M2EuNjkuNjkgMCAwIDAgLjczIDBsLTEuMTguN2EuNy43IDAgMCAxLS43NCAweiIgY2xhc3M9InN0MSIvPiYjeGE7CQk8cGF0aCBkPSJNMy4yMzYgNy44MDdhLjc2Ljc2IDAgMCAwLS4zNy42NXY1YTIuNzUgMi43NSAwIDAgMS0uODcgMiAuMTguMTggMCAwIDEtLjMtLjEzdi03LjU2YzAtLjI4IDEuNTQgMCAxLjU0IDB6IiBjbGFzcz0ic3QwIi8+JiN4YTsJCTxwYXRoIGQ9Ik02Ljc0NiA0LjUxN2EuMzQuMzQgMCAwIDEgLjM2IDBsMSAuNTktNi4wOCAzLjU2YS43Ny43NyAwIDAgMC0uMzcuNjZ2LTEuMzlhLjcyLjcyIDAgMCAxIC4zOC0uNjR6IiBjbGFzcz0ic3QxIi8+JiN4YTsJCTxwYXRoIGQ9Ik0xNS4xNDYgMTEuNDM3di01YTIuODEgMi44MSAwIDAgMSAuODQtMmMwIDAgLjMzLS4xMS4zMS4yMXMwIDcuMzcgMCA3LjM3Yy0uMzEuMzctMS42MSAwLTEuNjEgMGEuODEuODEgMCAwIDAgLjQ2LS41OHoiIGNsYXNzPSJzdDAiLz4mI3hhOwkJPHBhdGggZD0iTTE1Ljk3NiAxMi42MDdsLTQuNzQgMi44NWEuMzUuMzUgMCAwIDEtLjM3IDBsLTEtLjU3IDYuMTEtMy42N2EuNzcuNzcgMCAwIDAgLjM3LS42NnYxLjQ0Yy0uMDIuMjMtLjM3LjYxLS4zNy42MXoiIGNsYXNzPSJzdDEiLz4mI3hhOwk8L2c+JiN4YTs8L3N2Zz4=',
        'cloud cdn': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMTMuMTMgNS42M1YzLjIxTDEwIDB2Mi40MXptMy43NSA3LjVMMjAgMTBoLTIuNWwtMy4xMiAzLjEzem0tMTMuNzUgMEwwIDEwaDIuNWwzLjEzIDMuMTN6bTEwIDEuMjV2Mi40MUwxMCAyMHYtMi40MXoiIGZpbGwtcnVsZT0iZXZlbm9kZCIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik02Ljg4IDUuNjNMMTAgMi40MVYwTDYuODggMy4yMXpNMTcuNSAxMEgyMGwtMy4xMi0zLjEyaC0yLjV6bS0xNSAwSDBsMy4xMy0zLjEyaDIuNXptNC4zOCA0LjM4TDEwIDE3LjU5VjIwbC0zLjEyLTMuMjF6bTAtNy41aDYuMjV2Ni4yNUg2Ljg4eiIgZmlsbC1ydWxlPSJldmVub2RkIi8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTYuODggMTMuMTNsNi4yNS02LjI1djYuMjV6IiBmaWxsLXJ1bGU9ImV2ZW5vZGQiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTAgMTBsMy4xMy0zLjEydjYuMjV6IiBmaWxsLXJ1bGU9ImV2ZW5vZGQiLz4mI3hhOzwvc3ZnPg==',
        'cloud composer': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE0LjY0MDAwMDM0MzMyMjc1NCIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDE0LjY0MDAwMDM0MzMyMjc1NCAyMCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0MXtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTAgMGgxNC42M3YzLjk0aC01LjN2NS4zM0g1LjM1VjMuOTZIMHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMy45NSAxMC42N2g1LjM0VjIwSDUuMzV2LTUuMzVIMFY1LjM3aDMuOTV6TTE0LjY0IDIwSDEwLjdWNS4zNmgzLjk0eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0wIDE2LjA2aDMuOTJWMjBIMHoiLz4mI3hhOzwvc3ZnPg==',
        'cloud data fusion': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM3Ny4wNDk2OTgzMjc3ODkyNiIgaGVpZ2h0PSIzNzcuMjkxNTcwNzE1Nzg5NzYiIHZpZXdCb3g9IjAuMTMxMDAwNTE4Nzk4ODI4MTIgLTAuMTIxMDAwMDA2Nzk0OTI5NSA5OS43NjEwMDE1ODY5MTQwNiA5OS44MjQ5OTY5NDgyNDIxOSI+JiN4YTs8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qxe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MntmaWxsOiNhZWNiZmE7fSYjeGE7PC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNODAuNTkzIDE5LjE4djIwLjE5OWgxOS4yOTlWOS41M2MwLTIuNTM3LS45NzktNC44NDYtMi41OC02LjU2OHptLTkuOTA4IDYxLjIyNUgxOS40MzFMMy40NSA5Ny4zMzdjMS42OTUgMS40NzQgMy45MDggMi4zNjcgNi4zMzEgMi4zNjdoNzAuNTU1YzIuODczIDAgNS40NTMtMS4yNTYgNy4yMjEtMy4yNDh6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTg3LjU3MyA5Ni40MzdjMS41MDEtMS43MDEgMi40MTMtMy45MzUgMi40MTMtNi4zODJWNjAuMjA0SDcwLjY4NXYyMC4yMDF6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTE5LjQzMSA4MC40MDVWMjkuMzRoMjAuNTc4VjEwLjA0SDkuNzgxYy01LjMzIDAtOS42NSA0LjMyMS05LjY1IDkuNjV2NzAuMzY1Yy4wMDEgMi45MDYgMS4yODYgNS41MTMgMy4zMiA3LjI4MXptNzcuODgtNzcuNDQzQzk1LjU1IDEuMDY2IDkzLjAzNi0uMTIgOTAuMjQ0LS4xMjFINTkuOTUxVjE5LjE4aDIwLjY0M3oiLz4mI3hhOzwvc3ZnPg==',
        'cloud dns': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0M3tmaWxsOiNmZmY7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTkgNmgydjEwSDl6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTIwIDE3SDB2MmgyMHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMTIgMTZIOHY0aDR6TTAgMGgyMHY2SDB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwIDBoMTB2NkgxMHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QzIiBkPSJNMiAyaDJ2MkgyeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0wIDhoMjB2NkgweiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xMCA4aDEwdjZIMTB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MyIgZD0iTTIgMTBoMnYySDJ6Ii8+JiN4YTs8L3N2Zz4=',
        'cloud domains': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGhlaWdodD0iMjA0LjI1MTk1MzEyNSIgdmlld0JveD0iMCAwIDMzOC4yNDEzMDI0OTAyMzQ0IDIwNC4yNTE5NTMxMjUiIHByZXNlcnZlQXNwZWN0UmF0aW89InhNaWRZTWlkIG1lZXQiIHdpZHRoPSIzMzguMjQxMzAyNDkwMjM0NCIgdmVyc2lvbj0iMS4xIiBpZD0ic3ZnOTg3IiB6b29tQW5kUGFuPSJtYWduaWZ5Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgkuc3Qwe2ZpbGw6IzY2OWRmNjt9CS5zdDF7ZmlsbDojYWVjYmZhO30JPC9zdHlsZT4JJiN4YTsgIDxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0gMjcwLjM0MzY2LDE2MC4wMjA1MyAzMzguMjQxMywwIGggLTYwIE0gMTc2LjM0MzY2LDE2MC4wMjA1NCAyNDQuMjQxMywwIGggLTYwIE0gNTkuOTk5OTk5LDIwNC4yNTE5NSA4NS45ODg0NzksMTQ4LjIxNDg0IEggNjIuNjkxNDc1IG0gMS41OTIyMzYsLTMzLjcwNDAyIGggMzYuODE4MDU5IGwgMjUuOTg4NDgsLTU2LjAzNzEwMSBoIC02MCIvPiYjeGE7ICA8cGF0aCBjbGFzcz0ic3QxIiBkPSJtIDI3OC4yNDEzLDAgLTg2LjQ5MjkxLDIwMy44NDU2OSBoIDYwIGwgMTguNTk1MjcsLTQzLjgyNTE2IE0gMTg0LjI0MTMsMCA5Ny43NDgzOTEsMjAzLjg0NTcgaCA1OS45OTk5OTkgbCAxOC41OTUyNywtNDMuODI1MTYgTSA2Mi42OTE0NzUsMTQ4LjIxNDg0IEggMjUuOTg4NDggTCAwLDIwNC4yNTE5NSBIIDU5Ljk5OTk5OSBNIDY3LjA5MDI1LDU4LjQ3MzcxOSA0MS4xMDE3NywxMTQuNTEwODIgaCAyMy4xODE5NDEiLz4mI3hhOzwvc3ZnPg==',
        'cloud endpoints': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE5Ljk1MDAwMDc2MjkzOTQ1MyIgaGVpZ2h0PSIxMiIgdmlld0JveD0iMCAwIDE5Ljk1MDAwMDc2MjkzOTQ1MyAxMiI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNH0mI3hhOwkuc3Qxe2ZpbGw6I2FlY2JmYX0mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik02IDZsMSAyaDZsMS0yLTEtMkg3eiIgZmlsbD0iIzQyODVmNCIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik03LjUxIDRIN0w2IDZoOGwtMS0yeiIgZmlsbD0iI2FlY2JmYSIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xNi45NyA2bDEuNS0yLjI1TDE2IDBoLTN6IiBmaWxsPSIjNDI4NWY0Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE2Ljk3IDZoMEwxMyAxMmgzbDMuOTUtNi0xLjQ4LTIuMjV6IiBmaWxsPSIjYWVjYmZhIi8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTIuOTggNmwtMS41IDIuMjVMMy45NSAxMmgzeiIgZmlsbD0iIzQyODVmNCIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0yLjk4IDZoMGwzLjk3LTZoLTNMMCA2bDEuNDggMi4yNXoiIGZpbGw9IiNhZWNiZmEiLz4mI3hhOzwvc3ZnPg==',
        'cloud external ip addresses': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE5Ljk5OTk5ODA5MjY1MTM2NyIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAtMi44NDIxNzA1NjE4NzU1NzQ1ZS0xNSAxOS45OTk5OTgwOTI2NTEzNjcgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xNS40OSAxMC40djYuN2EuNC40IDAgMCAxLS40LjRIMi45YS40LjQgMCAwIDEtLjQtLjRWNC45YS40LjQgMCAwIDEgLjQtLjRoNi43YS40LjQgMCAwIDAgLjQtLjRWMi40YS40LjQgMCAwIDAtLjQtLjRILjRhLjQuNCAwIDAgMC0uNC40djE3LjJhLjQuNCAwIDAgMCAuNC40aDE3LjJhLjQuNCAwIDAgMCAuNC0uNHYtOS4yYS40LjQgMCAwIDAtLjQtLjRoLTEuNzFhLjQuNCAwIDAgMC0uNC40eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xMiAuNHY3LjJhLjQuNCAwIDAgMCAuNC40aDcuMmEuNC40IDAgMCAwIC40LS40Vi40YS40LjQgMCAwIDAtLjQtLjRoLTcuMmEuNC40IDAgMCAwLS40LjR6bTUuNiA0LjFoLTEuNzFhLjQuNCAwIDAgMS0uNC0uNFYyLjRhLjQuNCAwIDAgMSAuNC0uNGgxLjcxYS40LjQgMCAwIDEgLjQuNHYxLjdhLjQuNCAwIDAgMS0uNC40eiIvPiYjeGE7PC9zdmc+',
        'cloud firewall rules': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiBmaWxsPSIjNDI4NWY0IiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTAgMGg4Ljg5djIuMjJIMHptMCAxNy43OGg4Ljg5VjIwSDB6bTAtOC44OWg4Ljg5djIuMjJIMHpNMTEuMTEgMEgyMHYyLjIyaC04Ljg5em0wIDE3Ljc4SDIwVjIwaC04Ljg5em0wLTguODlIMjB2Mi4yMmgtOC44OXpNNS41NSA0LjQ0aDguODl2Mi4yMkg1LjU1em0wIDguODloOC44OXYyLjIySDUuNTV6TTAgNC40NGgzLjMzdjIuMjJIMHptMCA4Ljg5aDMuMzN2Mi4yMkgwem0xNi42Ny04Ljg5SDIwdjIuMjJoLTMuMzN6bTAgOC44OUgyMHYyLjIyaC0zLjMzeiIvPiYjeGE7PC9zdmc+',
        'cloud functions': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE5Ljk4OTk5OTc3MTExODE2NCIgdmlld0JveD0iMCAwIDIwIDE5Ljk4OTk5OTc3MTExODE2NCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDJ7ZmlsbDojYWVjYmZhO30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0zIDMuOTlMMCA2LjQydjcuMTNsMyAyLjQ0eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0zIDMuOTlsLTMgNCAzLTJ6bS0zIDhsMyA0di0yeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0wIDE1Ljk5bDQgNCAyLTItNi02em0uMDEtOEw1Ljk5IDJsLTItMkwwIDMuOTl6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE3IDE2bDMtMi40MlY2LjQ0TDE3IDR6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTE3IDE2bDMtNC0zIDJ6bTMtOGwtMy00djJ6Ii8+JiN4YTsJPGcgY2xhc3M9InN0MiI+JiN4YTsJCTxwYXRoIGQ9Ik0yMCA0bC00LTQtMiAyIDYgNnptLS4wMSA4bC01Ljk4IDUuOTkgMiAyTDIwIDE2eiIvPiYjeGE7CQk8Y2lyY2xlIGN4PSI2IiBjeT0iOS45OSIgcj0iMSIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIxMCIgY3k9IjkuOTkiIHI9IjEiLz4mI3hhOwkJPGNpcmNsZSBjeD0iMTMuOTkiIGN5PSI5Ljk5IiByPSIxIi8+JiN4YTsJPC9nPiYjeGE7PC9zdmc+',
        'cloud gpus': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNNyA3aDZ2Nkg3eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik05IDBoMnY0SDl6TTUgMGgydjRINXptOCAwaDJ2NGgtMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNOSAxNmgydjRIOXptLTQgMGgydjRINXptOCAwaDJ2NGgtMnptMy01VjloNHYyem0wIDR2LTJoNHYyem0wLThWNWg0djJ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTAgMTFWOWg0djJ6bTAgNHYtMmg0djJ6bTAtOFY1aDR2MnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMyAzdjE0aDE0VjN6bTEyIDEySDVWNWgxMHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMTAgMTBsLTMgM2g2eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xMyA3bC0zIDMgMyAzeiIvPiYjeGE7PC9zdmc+',
        'cloud iam': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE2LjQyMDAwMDA3NjI5Mzk0NSIgaGVpZ2h0PSIyMC4wNDk5OTkyMzcwNjA1NDciIGZpbGwtcnVsZT0iZXZlbm9kZCIgdmlld0JveD0iMCAwIDE2LjQyMDAwMDA3NjI5Mzk0NSAyMC4wNDk5OTkyMzcwNjA1NDciPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik04LjIxIDBMMCAzLjQydjUuNjNjMCA1LjA2IDMuNSA5LjggOC4yMSAxMSA0LjcxLTEuMTUgOC4yMS01Ljg5IDguMjEtMTAuOTVWMy40MnptMCAzLjc5YTIuNjMgMi42MyAwIDAgMSAxLjAwNSA1LjA2QTIuNjMgMi42MyAwIDAgMSA2LjM1IDQuNTZhMi42MyAyLjYzIDAgMCAxIDEuODYtLjc3em00LjExIDExLjE1YTguNjQgOC42NCAwIDAgMS00LjExIDIuOTMgOC42NCA4LjY0IDAgMCAxLTQuMTEtMi45M3YtMi4yNWMwLTEuNjcgMi43NC0yLjUyIDQuMTEtMi41MnM0LjExLjg1IDQuMTEgMi41MnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNOC4yMSAwdjMuNzlhMi42MyAyLjYzIDAgMSAxIDAgNS4yNnYxLjEyYzEuMzcgMCA0LjExLjg1IDQuMTEgMi41MnYyLjI1YTguNjQgOC42NCAwIDAgMS00LjExIDIuOTNWMjBjNC43MS0xLjE1IDguMjEtNS44OSA4LjIxLTEwLjk1VjMuNDJ6Ii8+JiN4YTs8L3N2Zz4=',
        'cloud inference api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM3NS41MDQwMTg5MTYxMTE2IiBoZWlnaHQ9IjM3Ni40MTEwMTA4NDIxNTg5MyIgdmlld0JveD0iMCAwIDk5LjM1MjAwNTAwNDg4MjgxIDk5LjU5MjAwMjg2ODY1MjM0Ij4mI3hhOzxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDF7ZmlsbDojYWVjYmZhO30mI3hhOzwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTcwLjc2MyA0OS43ODZhMzAuOTkgMzAuOTkgMCAwIDAtNC40OTkuNDQydjI3LjA3OGgxMXYtMjYuOTdsLTIuNjg2LS4zOTFjLTEuMjc5LS4xMzEtMi41NC0uMTg2LTMuODE1LS4xNTl6bS0xNS41ODcgMy43NjZsLTQuNDcxIDEuODcxLS4wMTYuMDA2LS4wMTYuMDA4LTYuNDk4IDIuNTIydjMwLjg4NGgxMXptMzMuMTc2LjEwNHY0NS45MzZoMTFWNTguMTk4Yy00LjEzOC0xLjc5OC03Ljc4My0zLjMyNS0xMS00LjU0MXpNMCA1My43Njh2MjMuNTM5aDExVjU4LjAxMmMtMy40MzYtMS4xMjYtNy4wNTItMi41NTItMTEtNC4yNDR6bTMzLjA4OCA2Ljg2Yy0zLjcwNS40NzItNy4zMjUuNDc4LTExIC4wMDd2MzguOTU3aDExeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0wIDB2NDEuNzM0YzQuMTA1IDEuODE5IDcuNzQgMy4zNSAxMSA0LjU3MlYwem02Ni4yNjQgMHYzOS4xNTRjMy4xNzgtLjQxMiA2LjI4Mi0uNDczIDkuNDM0LS4xNS41MjMuMDUzIDEuMDQ0LjExOSAxLjU2Ni4xOTFWMHpNNDQuMTc2IDExLjUzOHYzNC42OTRsMi4xMzctLjg5NWMzLjE0LTEuMzc5IDYuMDY5LTIuNTM5IDguODYzLTMuNDl2LTMwLjMxek0yMi4wODggMjIuMjg1djI3LjIzYy4wMTEuMDAyLjAyMi4wMDQuMDMzLjAwNiAzLjc3NC42NCA3LjIxNS43MDcgMTAuOTY3LjA4VjIyLjI4NXptNjYuMjY0IDB2MTkuNjQxYzMuMzg4IDEuMTQ0IDcuMDE1IDIuNTk3IDExIDQuMjlWMjIuMjg1eiIvPiYjeGE7PC9zdmc+',
        'cloud interconnect': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE4IiBmaWxsLXJ1bGU9ImV2ZW5vZGQiIHZpZXdCb3g9IjAgMCAyMCAxOCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDJ7ZmlsbDojYWVjYmZhO30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik00IDhIMHYyaDR6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTMgNGgxMHYxMEgzeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0yMCA4aC00LjY3djJIMjB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE1IDJ2MTRINnYyaDExdi0yVjIgMEg2djJ6TTggNGg1djEwSDh6Ii8+JiN4YTs8L3N2Zz4=',
        'cloud key management': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjMxMC43NzU2MDY1NDM4NjAyNSIgaGVpZ2h0PSIzNzcuOTUzMDI4ODM1NTI1NDYiIHZpZXdCb3g9Ii0wLjE0MDAwMDAwMDU5NjA0NjQ1IC0wLjQ2NzAwMDAwNzYyOTM5NDUzIDgyLjIyNTk5NzkyNDgwNDY5IDEwMC4wMDAwMDc2MjkzOTQ1MyI+JiN4YTs8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qxe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MntmaWxsOiNmZmY7fSYjeGE7PC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNNDAuOTczLS40NjdsNDEuMTEzIDE3LjQ5M3YyOS42NTRjMCAyNy40MTgtMjQuNjA4IDUwLjgzNi00MS4xMTMgNTIuODUzeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik00MC45NzMtLjQ2N0wtLjE0IDE3LjAyNXYyOS42NTRjMCAyNy40MTggMjQuNjA4IDUwLjgzNiA0MS4xMTMgNTIuODUzeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik00MS4yNTMgMTYuNjA1Yy05LjU4NCAwLTE3LjQ0NSA3Ljg2Mi0xNy40NDUgMTcuNDQ1IDAgOC4wODQgNS41OTQgMTQuOTQyIDEzLjA5NiAxNi44OTF2OS40ODhoLTkuODY5djguNzAxaDkuODY5djUuMzc3aC02LjMxNXY4LjcwMWg2LjMxNXYyLjE5N2g4LjcwMVY1MC45NDFDNTMuMTA2IDQ4Ljk5MiA1OC43IDQyLjEzNCA1OC43IDM0LjA1YzAtOS41ODQtNy44NjMtMTcuNDQ1LTE3LjQ0Ny0xNy40NDV6bTAgOC42OTlBOC42OCA4LjY4IDAgMCAxIDUwIDM0LjA1YTguNjggOC42OCAwIDAgMS04Ljc0OCA4Ljc0NiA4LjY4IDguNjggMCAwIDEtOC43NDYtOC43NDYgOC42OCA4LjY4IDAgMCAxIDguNzQ2LTguNzQ2eiIvPiYjeGE7PC9zdmc+',
        'cloud load balancing': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMTYgMTBoMnY0aC0yem0tNyAwaDJ2NEg5em0tNyAwaDJ2NEgyeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik05IDVoMnY0SDl6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTIgOWgxNnYySDJ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTQgMGgxMnY1SDR6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwIDBoNnY1aC02eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0xNCAxNGg2djZoLTZ6TTAgMTRoNnY2SDB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTMgMTRoM3Y2SDN6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTcgMTRoNnY2SDd6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwIDE0aDN2NmgtM3ptNyAwaDN2NmgtM3oiLz4mI3hhOzwvc3ZnPg==',
        'cloud nat': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI5OS45OTcyODY5NDYxMDM0MyIgaGVpZ2h0PSI5Ny44ODA4NTM5MDQyOTYzMyIgdmlld0JveD0iLTAuMDQ1Nzc2MzY3MTg3NSAxLjA4Nzc4NzYyODE3MzgyODEgOTkuOTk3MjgzOTM1NTQ2ODggOTcuODgwODQ0MTE2MjEwOTQiIHZlcnNpb249IjEuMSIgaWQ9InN2ZzUiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojNDI4NWY0O30JLnN0MXtmaWxsOiM2NjlkZjY7fQk8L3N0eWxlPgkmI3hhOyAgPGcgaWQ9ImxheWVyMSIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoMjU4LjYxOTc1LDE2LjY2NzcxNSkiPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0gMTQxLjQxNzk3LDQuMTExMzI4MSAxMjQuNDAyMzQsMjQuMzc1IGMgNTcuODk1MzcsNDguNjE2NDI2IDgzLjQxNDA3LDk2LjA2NDY3IDgzLjQxNDA3LDE2My45NDMzNiAwLDcyLjMxMjI4IC0zNi4xMDczMSwxMjQuODI5NzcgLTgyLjAxOTUzLDE2Ni4wNDg4MyBsIDE3LjY3OTY4LDE5LjY4NzUgYyA0OS4yMDI5OSwtNDQuMTczNDIgOTAuNzk2ODgsLTEwNC40OTgzNyA5MC43OTY4OCwtMTg1LjczNjMzIDAsLTc0Ljg4MTUyIC0zMS4xNTk0MSwtMTMyLjM5OTAyMiAtOTIuODU1NDcsLTE4NC4yMDcwMzE5IHogTSA5Ni41NTY2NDEsNzUuODg0NzY2IFYgMTAyLjM0MTggSCAxNjYuNDgzMDUgQyAxNjIuMzkyNzQsOTQuNTU0NDIgMTU4LjQ1MTQzLDg2Ljg0MTU0MiAxNDguMDIyMzMsNzUuODg0NzY2IFogTSAzMTcuNzc5MywyMDIuMzA2NjQgdiAzMi4yOTI5NyBsIDU5Ljk5MDIzLC00NS41MTc1OCAtNTkuOTkwMjMsLTQ1LjUxNzU4IHYgMzIuMjg1MTYgaCAtNjQuNDc0NjEgdiAyNi40NTcwMyB6IE0gNTAuMDU4NTk0LDE3NS44NDk2MSB2IDI2LjQ1NzAzIEggMTg3LjI4MTI1IGMgMS4xNTc0NSwtOC4wNDczNyAxLjI4MjMxLC0xNi43ODMxNSAwLC0yNi40NTcwMyB6IG0gNDcuMDM3MTA5LDEwMC4wNDY4NyB2IDI2LjQ1NzA0IGggNTAuNjgyNjc3IGMgOC4wMTY1NywtOC4wMTQ2NiAxNC40NjE2OSwtMTYuODE1MDQgMTkuMjIzNTcsLTI2LjQ1NzA0IHoiIHRyYW5zZm9ybT0ibWF0cml4KDAuMjY0NTgzMzMsMCwwLDAuMjY0NTgzMzMsLTI1OC42MTk3NSwtMTYuNjY3NzE1KSIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDEiIGQ9Im0gLTIzNy45NTQwOCw1MS45MDU2ODYgYyAtNC4zNDYzLDEwZS03IC03LjkyMzgyLDMuNTc3NTIxIC03LjkyMzgyLDcuOTIzODI4IDAsNC4zNDYzMDcgMy41Nzc1Miw3LjkyMzgyOCA3LjkyMzgyLDcuOTIzODI4IDQuMzQ2MzEsMCA3LjkyMzgzLC0zLjU3NzUyMSA3LjkyMzgzLC03LjkyMzgyOCAwLC00LjM0NjMwNyAtMy41Nzc1MiwtNy45MjM4MjcgLTcuOTIzODMsLTcuOTIzODI4IHogbSAwLDUgYyAxLjY0NDExLDAgMi45MjM4MywxLjI3OTcxOCAyLjkyMzgzLDIuOTIzODI4IDAsMS42NDQxMSAtMS4yNzk3MiwyLjkyMzgyOCAtMi45MjM4MywyLjkyMzgyOCAtMS42NDQxMSwwIC0yLjkyMzgyLC0xLjI3OTcxOCAtMi45MjM4MiwtMi45MjM4MjggMCwtMS42NDQxMSAxLjI3OTcxLC0yLjkyMzgyOCAyLjkyMzgyLC0yLjkyMzgyOCB6IG0gLTEyLjc4NzYxLC0zMS40ODg1OTMgYyAtNC4zNDYzLDEwZS03IC03LjkyMzgyLDMuNTc3NTIxIC03LjkyMzgyLDcuOTIzODI4IDAsNC4zNDYzMDcgMy41Nzc1Miw3LjkyMzgyOCA3LjkyMzgyLDcuOTIzODI4IDQuMzQ2MzEsMCA3LjkyMzgzLC0zLjU3NzUyMSA3LjkyMzgzLC03LjkyMzgyOCAwLC00LjM0NjMwNyAtMy41Nzc1MiwtNy45MjM4MjcgLTcuOTIzODMsLTcuOTIzODI4IHogbSAwLDUgYyAxLjY0NDExLDAgMi45MjM4MywxLjI3OTcxOCAyLjkyMzgzLDIuOTIzODI4IDAsMS42NDQxMSAtMS4yNzk3MiwyLjkyMzgyOCAtMi45MjM4MywyLjkyMzgyOCAtMS42NDQxMSwwIC0yLjkyMzgyLC0xLjI3OTcxOCAtMi45MjM4MiwtMi45MjM4MjggMCwtMS42NDQxMSAxLjI3OTcxLC0yLjkyMzgyOCAyLjkyMzgyLC0yLjkyMzgyOCB6IG0gMTIuNjE2NTIsLTMxLjQzMTQ5MjkgYyAtNC4zNDYzLDZlLTcgLTcuOTIzODIsMy41Nzc1MjA4IC03LjkyMzgyLDcuOTIzODI4MSAwLDQuMzQ2MzA2OCAzLjU3NzUyLDcuOTIzODI3OCA3LjkyMzgyLDcuOTIzODI3OCA0LjM0NjMxLDAgNy45MjM4MywtMy41Nzc1MjEgNy45MjM4MywtNy45MjM4Mjc4IDAsLTQuMzQ2MzA3MyAtMy41Nzc1MiwtNy45MjM4Mjc1IC03LjkyMzgzLC03LjkyMzgyODEgeiBtIDAsNSBjIDEuNjQ0MTEsMmUtNyAyLjkyMzgzLDEuMjc5NzE4NCAyLjkyMzgzLDIuOTIzODI4MSAwLDEuNjQ0MTA5NiAtMS4yNzk3MiwyLjkyMzgyNzkgLTIuOTIzODMsMi45MjM4Mjc5IC0xLjY0NDExLDAgLTIuOTIzODIsLTEuMjc5NzE4MyAtMi45MjM4MiwtMi45MjM4Mjc5IDAsLTEuNjQ0MTA5NyAxLjI3OTcxLC0yLjkyMzgyNzkgMi45MjM4MiwtMi45MjM4MjgxIHoiLz4mI3hhOyAgPC9nPiYjeGE7PC9zdmc+',
        'cloud natural language api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE2IiB2aWV3Qm94PSIwIDAgMjAgMTYiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDF7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTUgMmgzdjEyaC0zdjJoMyAydi0yVjIgMGgtMi0zeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xOCAydjFsMi0xem0yIDEydi0xbC0yIDF6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTUgMTRIMlYyaDNWMEgyIDB2MiAxMiAyaDIgM3oiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMCAxNHYtMWwyIDF6TTIgMnYxTDAgMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNNSA3aDEwdjJINXptMCAzaDEwdjJINXptMC02aDEwdjJINXoiLz4mI3hhOzwvc3ZnPg==',
        'cloud network': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE4Ljc1OTk5ODMyMTUzMzIwMyIgdmlld0JveD0iMCAwIDIwIDE4Ljc1OTk5ODMyMTUzMzIwMyI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDJ7ZmlsbDojYWVjYmZhO30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xMC42MiAxNi40NUw0LjMgMTAuMzFsLTEuMzYuNzcgNi41OSA2LjUyem01LjA3LTcuNjNsMS43OC0uMzgtNi45LTdMOS40OCAyLjZ6IiBmaWxsLXJ1bGU9ImV2ZW5vZGQiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNOS4zOCAyLjUxaDEuMjV2NUg5LjM4em0wIDkuMzdoMS4yNXY1SDkuMzh6Ii8+JiN4YTsJPGcgY2xhc3M9InN0MiI+JiN4YTsJCTxjaXJjbGUgY3g9IjEwIiBjeT0iMS44OCIgcj0iMS44OCIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIxMCIgY3k9IjE2Ljg4IiByPSIxLjg4Ii8+JiN4YTsJPC9nPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xOS4zNyAxMC42M0g0LjNMLjY2IDguNzZoMTUuMDd6IiBmaWxsLXJ1bGU9ImV2ZW5vZGQiLz4mI3hhOwk8ZyBjbGFzcz0ic3QyIj4mI3hhOwkJPGNpcmNsZSBjeD0iMi41IiBjeT0iOS42OSIgcj0iMi41Ii8+JiN4YTsJCTxjaXJjbGUgY3g9IjE3LjUiIGN5PSI5LjY5IiByPSIyLjUiLz4mI3hhOwk8L2c+JiN4YTs8L3N2Zz4=',
        'cloud resource manager': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE2LjQyMDAwMDA3NjI5Mzk0NSIgaGVpZ2h0PSIyMC4wNDk5OTkyMzcwNjA1NDciIGZpbGwtcnVsZT0iZXZlbm9kZCIgdmlld0JveD0iMCAwIDE2LjQyMDAwMDA3NjI5Mzk0NSAyMC4wNDk5OTkyMzcwNjA1NDciPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik04LjIxIDBMMCAzLjQydjUuNjNjMCA1LjA2IDMuNSA5LjggOC4yMSAxMSA0LjcxLTEuMTUgOC4yMS01Ljg5IDguMjEtMTAuOTVWMy40MnptMCAzLjc5YTIuNjMgMi42MyAwIDAgMSAxLjAwNSA1LjA2QTIuNjMgMi42MyAwIDAgMSA2LjM1IDQuNTZhMi42MyAyLjYzIDAgMCAxIDEuODYtLjc3em00LjExIDExLjE1YTguNjQgOC42NCAwIDAgMS00LjExIDIuOTMgOC42NCA4LjY0IDAgMCAxLTQuMTEtMi45M3YtMi4yNWMwLTEuNjcgMi43NC0yLjUyIDQuMTEtMi41MnM0LjExLjg1IDQuMTEgMi41MnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNOC4yMSAwdjMuNzlhMi42MyAyLjYzIDAgMSAxIDAgNS4yNnYxLjEyYzEuMzcgMCA0LjExLjg1IDQuMTEgMi41MnYyLjI1YTguNjQgOC42NCAwIDAgMS00LjExIDIuOTNWMjBjNC43MS0xLjE1IDguMjEtNS44OSA4LjIxLTEwLjk1VjMuNDJ6Ii8+JiN4YTs8L3N2Zz4=',
        'cloud router': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTE3IDEydjNsLTUtNSA1LTV2M2gzdjR6TTMgOEgwdjRoM3YzbDUtNS01LTV6bTkgN3YtM0g4djNINWw1IDUgNS01em0wLTEwdjNIOFY1SDVsNS01IDUgNXoiLz4mI3hhOzwvc3ZnPg==',
        'cloud routes': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE5LjI5OTk5OTIzNzA2MDU0NyIgdmlld0JveD0iMCAwIDIwIDE5LjI5OTk5OTIzNzA2MDU0NyI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTIuNDMgNi4xSDBWMi42N2gzLjk0bDguNCAxMC40OWgyLjM0di0yLjcyTDIwIDE0Ljg3bC01LjMyIDQuNDN2LTIuNzFoLTMuODd6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE0LjY4IDYuMTR2Mi43MkwyMCA0LjQzIDE0LjY4IDB2Mi43MWgtMy44N0w4LjMzIDUuODJsMi4xMyAyLjY3IDEuODgtMi4zNXpNMCAxMy4ydjMuNDNoMy45NGwyLjUyLTMuMTUtMi4xMy0yLjY3LTEuOSAyLjM5eiIvPiYjeGE7PC9zdmc+',
        'cloud run': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM2NS40NjQ5OTY3NzA0MjQ5MyIgaGVpZ2h0PSIzNzkuMjIyOTk0NDYzNTc3OTUiIHZpZXdCb3g9IjAgMCA5Ni42OTU5OTkxNDU1MDc4MSAxMDAuMzM1OTk4NTM1MTU2MjUiPiYjeGE7PHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiNhZWNiZmE7fSYjeGE7PC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMjkuNzk0IDEwMC4zMzZMNDYuOTIgNTAuMTY4aDQ5Ljc3NnpNMCA5OS42NzFsMTIuOTc2LTQ5LjUwMkgyOS4yMkwxNi44OTcgOTIuMDU0eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0yOS43OTQgMEw0Ni45MiA1MC4xNjhoNDkuNzc2ek0wIC42NjZsMTIuOTc2IDQ5LjUwMkgyOS4yMkwxNi44OTcgOC4yODN6Ii8+JiN4YTs8L3N2Zz4=',
        'cloud scheduler': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM2MC4zMDM3NjY4NjA4MzYzIiBoZWlnaHQ9IjM3OC4wNTExNTgwNzc0MDg4IiB2aWV3Qm94PSItMC4wMDAxNjI0MjExNDM2MTM3NTU3IC0wLjAwMDEwMDAwNTk0OTIwNzExNTkyIDk1LjMzMDI2MTIzMDQ2ODc1IDEwMC4wMjYxMDAxNTg2OTE0Ij4mI3hhOzxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojYWVjYmZhO30mI3hhOwkuc3Qye2ZpbGw6IzY2OWRmNjt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik03OS45NzEgNzcuNzE1bC03LjM1OSA3LjQ4OCA4LjYzOSA4LjQ5IDcuMzU5LTcuNDg4em0tNjUuMDk2LjA2MWwtOC42NDEgOC40OTIgNy4zNjEgNy40ODggOC42MzktOC40OXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNNzkuNTUzLjIyMWE1LjI1IDUuMjUgMCAwIDAtMy42NiA4Ljk4NEw4Ni4zODkgMTkuNThhNS4yNSA1LjI1IDAgMCAwIDguOTQxLTMuNzY1IDUuMjUgNS4yNSAwIDAgMC0xLjU2LTMuNzA0TDgzLjI3NSAxLjczOEE1LjI1IDUuMjUgMCAwIDAgNzkuNTUzLjIyMXpNMTUuOTE2IDBhNS4yNSA1LjI1IDAgMCAwLTMuNzIzIDEuNTE2TDEuNjk5IDExLjg5MWE1LjI1IDUuMjUgMCAwIDAtLjA0MyA3LjQyNCA1LjI1IDUuMjUgMCAwIDAgNy40MjQuMDQzTDE5LjU3NiA4Ljk4MkE1LjI1IDUuMjUgMCAwIDAgMTUuOTE2IDB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTQ4LjEzOCAyNi4yNGMxMy4zNDcgMCAyNS40MzIgMTEuMTM2IDI1LjMxIDI2LjQ4MSAwIDE1LjExLTEyLjI2NyAyNS42NzMtMjUuMTg5IDI1LjY3My0xMS4xNDkgMC0xOC4zMTctNS4xNzEtMjEuOTYtMTAuNzM4bDIxLjgzOS0xNS4wOTd6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTgxLjI1IDkzLjY5M2w0LjY2NCA0LjU4NmE1LjI1IDUuMjUgMCAxIDAgNy4zNjEtNy40OWwtNC42NjYtNC41ODR6TTYuMjM0IDg2LjI2OEwxLjU3IDkwLjg1MWE1LjI1IDUuMjUgMCAwIDAtLjA2NSA3LjQyNCA1LjI1IDUuMjUgMCAwIDAgNy40MjQuMDY0bDQuNjY2LTQuNTg0ek00Ny4zNzEgNS41NzhDMjEuMzQ5IDUuNTc4LjE0NiAyNi43NzkuMTQ2IDUyLjgwMXMyMS4yMDMgNDcuMjI1IDQ3LjIyNSA0Ny4yMjUgNDcuMjI1LTIxLjIwMyA0Ny4yMjUtNDcuMjI1UzczLjM5MyA1LjU3OCA0Ny4zNzEgNS41Nzh6bTAgMTBhMzcuMTUgMzcuMTUgMCAwIDEgMzcuMjI1IDM3LjIyM2MwIDIwLjYxNy0xNi42MDcgMzcuMjI1LTM3LjIyNSAzNy4yMjVTMTAuMTQ2IDczLjQxOCAxMC4xNDYgNTIuODAxYTM3LjE1IDM3LjE1IDAgMCAxIDM3LjIyNS0zNy4yMjN6Ii8+JiN4YTs8L3N2Zz4=',
        'cloud spanner': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE4LjQ1OTk5OTA4NDQ3MjY1NiIgZmlsbC1ydWxlPSJldmVub2RkIiB2aWV3Qm94PSIwIDAgMjAgMTguNDU5OTk5MDg0NDcyNjU2Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CQkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJCS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkJLnN0MntmaWxsOiNhZWNiZmE7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTguNjYgNS42M3Y0LjM2bC0zLjc3IDIuMTggMS4zNCAyLjMyTDEwIDEyLjMxbDMuNzcgMi4xOCAxLjM0LTIuMzItMy43Ny0yLjE4VjUuNjN6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTEwIDUuNjN2NS4xMmwtNC40NCAyLjU4LjY3IDEuMTZMMTAgMTIuMzFsMy43NyAyLjE4IDEuMzQtMi4zMi0zLjc3LTIuMThWNS42M3oiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNNi42MiA0Ljk1TDEwIDYuNzhWMy42N2wtMS4zNS0uNjJWMEw2LjYyIDEuMjJ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwIDYuNzhsMy4zOC0xLjgzVjEuMjJMMTEuMzUgMHYzLjA1TDEwIDMuNjd6bTYuMTQgNy41M2wtLjA4IDEuMzkgMi43IDEuNTMtMi4xOCAxLjItMy4yNC0xLjg3LjExLTMuODMgMy4yNy0yTDIwIDEyLjYxdjIuNDlsLTIuNjktMS41NXptLTEyLjI4IDBsLTEuMTctLjc2TDAgMTUuMXYtMi40OWwzLjIzLTEuODcgMy4yNyAyIC4xMSAzLjgzLTMuMTkgMS44OS0yLjE4LTEuMjMgMi43LTEuNTZ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTE2LjcyIDEwLjc1bC0zLjI3IDIuMDEgMi42OSAxLjU1IDEuMTYtLjc2TDIwIDE1LjFsLS4wNS0yLjQ5ek0zLjg2IDE0LjMxbDIuNjktMS41NS0zLjI3LTIuMDEtMy4yMyAxLjg2TDAgMTUuMWwyLjctMS41NXoiLz4mI3hhOzwvc3ZnPg==',
        'cloud sql': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE0LjY1OTk5OTg0NzQxMjExIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMTQuNjU5OTk5ODQ3NDEyMTEgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8c3R5bGU+JiN4YTsJCS5Ee2ZpbGwtcnVsZTpldmVub2RkfSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggZD0iTTcuMzMgMTUuMzV2LTMuMDFMMCA4LjQ0djMuMDF6bTAgNC42NXYtMy4wMUwwIDEzLjA5djMuMDF6IiBjbGFzcz0ic3QyIEQiLz4mI3hhOwk8cGF0aCBkPSJNMTQuNjYgOC40NGwtNy4zMyAzLjl2My4wMWw3LjMzLTMuOXptMCA0LjY1bC03LjMzIDMuOVYyMGw3LjMzLTMuOXoiIGNsYXNzPSJzdDEgRCIvPiYjeGE7CTxwYXRoIGQ9Ik03LjMzIDB2My4wMWw3LjMzIDMuOVYzLjl6IiBjbGFzcz0ic3QwIEQiLz4mI3hhOwk8cGF0aCBkPSJNMCA2LjkxbDcuMzMtMy45VjBMMCAzLjl6IiBjbGFzcz0iRCBzdDEiLz4mI3hhOwk8cGF0aCBkPSJNNy4zMyAxMC43OVY3Ljc3TDAgMy44N3YzLjAyeiIgY2xhc3M9IkQgc3QyIi8+JiN4YTsJPHBhdGggZD0iTTE0LjY2IDMuODdsLTcuMzMgMy45djMuMDJsNy4zMy0zLjl6IiBjbGFzcz0iRCBzdDEiLz4mI3hhOzwvc3ZnPg==',
        'cloud storage': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE2IiB2aWV3Qm94PSIwIDAgMjAgMTYiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0M3tmaWxsOiNmZmY7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTAgMGgyMHY3SDB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE4IDBoMnY3aC0yeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xOCA3bDItN2gtMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMCAwaDJ2N0gweiIvPiYjeGE7CTxnIGNsYXNzPSJzdDMiPiYjeGE7CQk8cGF0aCBkPSJNNCAzaDZ2MUg0eiIvPiYjeGE7CQk8cmVjdCB4PSIxMyIgeT0iMiIgd2lkdGg9IjMiIGhlaWdodD0iMyIgcng9IjEuNSIvPiYjeGE7CTwvZz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMCA5aDIwdjdIMHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMTggOWgydjdoLTJ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTE4IDE2bDItN2gtMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMCA5aDJ2N0gweiIvPiYjeGE7CTxnIGNsYXNzPSJzdDMiPiYjeGE7CQk8cGF0aCBkPSJNNCAxMmg2djFINHoiLz4mI3hhOwkJPHJlY3QgeD0iMTMiIHk9IjExIiB3aWR0aD0iMyIgaGVpZ2h0PSIzIiByeD0iMS41Ii8+JiN4YTsJPC9nPiYjeGE7PC9zdmc+',
        'cloud talent solutions': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE5LjkyMTQ0MjAzMTg2MDM1IiBoZWlnaHQ9IjE5Ljc3ODMyMDMxMjUiIHZpZXdCb3g9Ii0wLjAwMDQ0MTU1NzE3NDc4MTMzNzQgMC4yNSAxOS45MjE0NDIwMzE4NjAzNSAxOS43NzgzMjAzMTI1Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qxe2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0MntmaWxsLXJ1bGU6ZXZlbm9kZH0mI3hhOwkuc3Qze2ZpbGw6IzY2OWRmNjt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNNC40NjEgMTYuMjRhMyAzIDAgMSAxIDAtNiAzIDMgMCAxIDEgMCA2em0zLjYzLS40YTQuNDMgNC40MyAwIDAgMC01LjA0OS02LjcxNEE0LjQzIDQuNDMgMCAwIDAgLjAxMSAxMy4zMmE0LjkxIDQuOTEgMCAwIDAgMCAuNjcgMy40MyAzLjQzIDAgMCAwIC4wOS40NGwuMDYuMjFhNC41OSA0LjU5IDAgMCAwIC4zNC43OSA0LjI0IDQuMjQgMCAwIDAgLjc2IDFsLjE1LjE1LjMzLjI3YTQuMTYgNC4xNiAwIDAgMCAuNzMuNDQgNC40NCA0LjQ0IDAgMCAwIDQuNTQtLjI5bDIuOTMgMi45M2EuMzMuMzMgMCAwIDAgLjQ3IDBsLjY2LS42NWEuMzMuMzMgMCAwIDAgMC0uNDd6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTkuODExIDE0LjU4YTUuNDEgNS40MSAwIDAgMCAuMi0xLjUxIDUuNTMgNS41MyAwIDAgMC01LjYxLTUuNDIgNS44MiA1LjgyIDAgMCAwLTEuOTIuMzVWMy44M2EuNjIuNjIgMCAwIDEgLjYyLS42MmgxNi4xOWEuNjMuNjMgMCAwIDEgLjYzLjYyVjE0YS42My42MyAwIDAgMS0uNjMuNjN6Ii8+JiN4YTsJPGcgY2xhc3M9InN0MiI+JiN4YTsJCTxwYXRoIGNsYXNzPSJzdDMiIGQ9Ik0xMy41OTEgMy4yMVYxLjczaC00LjQ0djEuNDhoLTEuNDlWLjg3YS42My42MyAwIDAgMSAuNjMtLjYyaDYuMTZhLjYyLjYyIDAgMCAxIC42Mi42MnYyLjM0eiIvPiYjeGE7CQk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTUuMDcxIDMuMjFoLTEuNDhsMS40OC0uNDd6bS01LjkzIDBoLTEuNDlsMS40OS0uNTR6Ii8+JiN4YTsJPC9nPiYjeGE7PC9zdmc+',
        'cloud tasks': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM3Ni4zNDk5ODYzODk2NDkzNiIgaGVpZ2h0PSIzMDcuNjg0MDE3OTkzMzY5MjUiIHZpZXdCb3g9IjAgMCA5OS41NzU5OTYzOTg5MjU3OCA4MS40MDgwMDQ3NjA3NDIxOSI+JiN4YTs8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qxe2ZpbGw6IzQyODVmNDt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0wIDB2NDAuODc1aDEwVjB6bTIyLjM5NCAwdjQwLjg3NWgxMFYwem0yMi4zOTQgMHY0MC44NzVoMTBWMHptMjIuMzk0IDB2NDAuODc1aDEwVjB6bTIyLjM5NCAwdjQwLjg3NWgxMFYweiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik04OS41NzYgNDAuODc1djQwLjUzM2gxMFY0MC44NzV6bS0yMi4zOTQgMHY0MC41MzNoMTBWNDAuODc1em0tMjIuMzk0IDB2NDAuNTMzaDEwVjQwLjg3NXptLTIyLjM5NCAwdjQwLjUzM2gxMFY0MC44NzV6TTAgNDAuODc1djQwLjUzM2gxMFY0MC44NzV6Ii8+JiN4YTs8L3N2Zz4=',
        'cloud tpu': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE4IiBoZWlnaHQ9IjE4IiB2aWV3Qm94PSIwIDAgMTggMTgiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxnIGNsYXNzPSJzdDAiIGZpbGw9IiM0Mjg1ZjQiPiYjeGE7CQk8cGF0aCBkPSJNMy40OCA2LjYyYS4zNy4zNyAwIDAgMS0uMzU4LS41MzMuMzcuMzcgMCAwIDEgLjMwOC0uMjA3bDIuMy0uMzJhLjM3LjM3IDAgMCAxIC40Mi4zMi4zOC4zOCAwIDAgMS0uMzIuNDNsLTIuMy4zMXoiLz4mI3hhOwkJPHBhdGggZD0iTTYuMjk5IDYuMjkybC4yMzMtLjcxMyA0LjE0NSAxLjM1Mi0uMjMzLjcxM3oiLz4mI3hhOwkJPHBhdGggZD0iTTYuMTggNi4xNmgtLjExYS4zNy4zNyAwIDAgMS0uMjQtLjQ2bC44My0yLjg0YS4zNy4zNyAwIDAgMSAuNDYtLjI0LjM2LjM2IDAgMCAxIC4yNi40NWwtLjg0IDIuODFhLjM4LjM4IDAgMCAxLS4zNi4yOHptNS4xMyAxLjRBLjM2LjM2IDAgMCAxIDExIDdsMS42Ny00LjIzYS4zOC4zOCAwIDAgMSAuNDctLjE4LjM4LjM4IDAgMCAxIC4yMy40NWwtMS42OCA0LjI0YS4zOS4zOSAwIDAgMS0uMzguMjh6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik0yLjY2OSAxMy42MDRMNi42IDEwLjQ2NWwuNDY4LjU4Ni0zLjkzMSAzLjEzOXpNMTUuMDUgOC42MWwtLjMuNjgtMy42My0xLjU4LjI5LS42OXptLS4zMSA1LjQ4bC0uNTIuNTQtMy4yMy0zLjA0LjUyLS41NXpNNS43ODggNi4xMTNsLjczNS0uMTQ5LjgwOCAzLjk3OS0uNzM1LjE0OXoiLz4mI3hhOwkJPHBhdGggZD0iTTExLjU2IDcuNTZsLTQuMSAzLjYtLjUtLjU2IDQuMS0zLjZ6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik0xMS43NCA3LjNsLS4yNSAzLjk3LS43NC0uMDUuMjQtMy45N3oiLz4mI3hhOwkJPGNpcmNsZSBjeD0iNy4wMSIgY3k9IjEwLjgyIiByPSIxLjM2Ii8+JiN4YTsJCTxjaXJjbGUgY3g9IjExLjM3IiBjeT0iNy4zNiIgcj0iMS42MSIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIxMS4zNiIgY3k9IjExLjU0IiByPSIuODQiLz4mI3hhOwkJPGNpcmNsZSBjeD0iNi4wNCIgY3k9IjUuNjciIHI9Ii45OSIvPiYjeGE7CTwvZz4mI3hhOwk8ZyBjbGFzcz0ic3QxIiBmaWxsPSIjNjY5ZGY2Ij4mI3hhOwkJPHBhdGggZD0iTTggNGgyVjBIOHptNCAwaDJWMGgtMnpNNCA0aDJWMEg0em00IDE0aDJ2LTRIOHoiLz4mI3hhOwkJPHBhdGggZD0iTTEyIDE4aDJ2LTRoLTJ6bS04IDBoMnYtNEg0em0tNC04aDRWOEgwem0wLTRoNFY0SDB6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik0wIDE0aDR2LTJIMHptMTQtNGg0VjhoLTR6bTAtNGg0VjRoLTR6bTAgOGg0di0yaC00eiIvPiYjeGE7CQk8cGF0aCBkPSJNMTUgMkgzYTEgMSAwIDAgMC0xIDF2MTJhMSAxIDAgMCAwIDEgMWgxMmExIDEgMCAwIDAgMS0xVjNhMSAxIDAgMCAwLTEtMXptLTEgMTEuNDdhLjUzLjUzIDAgMCAxLS41My41M0g0LjUzYS41My41MyAwIDAgMS0uNTMtLjUzVjQuNTNBLjUzLjUzIDAgMCAxIDQuNTMgNGg4Ljk0YS41My41MyAwIDAgMSAuNTMuNTN6Ii8+JiN4YTsJPC9nPiYjeGE7PC9zdmc+',
        'cloud video intelligence api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE5Ljk4OTk5OTc3MTExODE2NCIgaGVpZ2h0PSIxNCIgdmlld0JveD0iMCAwIDE5Ljk4OTk5OTc3MTExODE2NCAxNCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MXtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTEwLjI3IDIuMzNoMi4wNXYxLjMzSDkuNEw3LjA3IDBIMHY0LjMzaDEuOTlMMy4yNSAyaDIuNTdsLjg2IDEuMzNINC4xMUwyLjg1IDUuNjZIMHYyLjU5aDIuODVsMS4yNiAyLjQxaDIuNTdMNS44MiAxMkgzLjI1TDEuOTkgOS42NkgwVjE0aDcuMDdsMi4zMy0zLjY3aDIuOTJ2MS4zM2gtMi4wNUw4LjggMTRoNS41MlY3LjY2SDcuOTFMNy4wOCA5SDUuMjRMNi41IDcgNS4yNCA1aDEuODRsLjggMS4zM2g2LjQ0VjBIOC44eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xNS45OSAxMC4xMWw0IDIuOTVWMS4xbC00IDIuOTF6Ii8+JiN4YTs8L3N2Zz4=',
        'cloud vision api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE2IiB2aWV3Qm94PSIwIDAgMjAgMTYiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDF7ZmlsbDojYWVjYmZhO30mI3hhOwkuc3Qye2ZpbGw6IzQyODVmNDt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8ZyBjbGFzcz0ic3QwIj4mI3hhOwkJPHBhdGggZD0iTTEwIDE2TDAgOGg0bDYgNC45OXoiLz4mI3hhOwkJPHBhdGggZD0iTTIwIDhsLTEwIDh2LTMuMDFMMTYgOHoiLz4mI3hhOwk8L2c+JiN4YTsJPGcgY2xhc3M9InN0MSI+JiN4YTsJCTxwYXRoIGQ9Ik0xMCAzLjAxTDQgOEgwbDEwLTh6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik0yMCA4TDEwIDB2My4wMUwxNiA4eiIvPiYjeGE7CTwvZz4mI3hhOwk8Y2lyY2xlIGNsYXNzPSJzdDIiIGN4PSIxMCIgY3k9IjgiIHI9IjIiLz4mI3hhOzwvc3ZnPg==',
        'cloud vpn': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE3Ljk1MDAwMDc2MjkzOTQ1MyIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDE3Ljk1MDAwMDc2MjkzOTQ1MyAyMCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPGcgY2xhc3M9InN0MSI+JiN4YTsJCTxwYXRoIGQ9Ik0xMS43IDkuMjhoNC4xOHYxLjM4SDExLjd6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik0xNC45MiA0LjEyaDEuMzh2MTEuNzFoLTEuMzh6Ii8+JiN4YTsJPC9nPiYjeGE7CTxnIGNsYXNzPSJzdDAiPiYjeGE7CQk8cmVjdCB4PSIxMy4yNyIgeT0iMTUuMzIiIHdpZHRoPSI0LjY4IiBoZWlnaHQ9IjQuNjgiIHJ4PSIuMjgiLz4mI3hhOwkJPHJlY3QgeD0iMTMuMjciIHdpZHRoPSI0LjY4IiBoZWlnaHQ9IjQuNjgiIHJ4PSIuMjgiLz4mI3hhOwk8L2c+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTMuOTUgOS4yOGg0LjI4djEuMzhIMy45NXoiLz4mI3hhOwk8ZyBjbGFzcz0ic3QwIj4mI3hhOwkJPHJlY3QgeT0iNy42MyIgd2lkdGg9IjQuNjgiIGhlaWdodD0iNC42OCIgcng9Ii4yOCIvPiYjeGE7CQk8cGF0aCBkPSJNOS45NyAxMi4xN2EyLjIgMi4yIDAgMSAxIDAtNC40IDIuMiAyLjIgMCAwIDEgMi4yIDIuMiAyLjE5IDIuMTkgMCAwIDEtMi4yIDIuMnptMC0zLjU3YTEuMzggMS4zOCAwIDAgMC0xLjA1IDIuMzNBMS4zOCAxLjM4IDAgMCAwIDExLjMgMTBhMS4zNyAxLjM3IDAgMCAwLTEuMzMtMS40eiIvPiYjeGE7CTwvZz4mI3hhOzwvc3ZnPg==',
        'compute engine': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNNyA3aDZ2Nkg3eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik05IDBoMnY0SDl6TTUgMGgydjRINXptOCAwaDJ2NGgtMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNOSAxNmgydjRIOXptLTQgMGgydjRINXptOCAwaDJ2NGgtMnptMy01VjloNHYyem0wIDR2LTJoNHYyem0wLThWNWg0djJ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTAgMTFWOWg0djJ6bTAgNHYtMmg0djJ6bTAtOFY1aDR2MnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMyAzdjE0aDE0VjN6bTEyIDEySDVWNWgxMHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMTAgMTBsLTMgM2g2eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xMyA3bC0zIDMgMyAzeiIvPiYjeGE7PC9zdmc+',
        'contact center ai': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc0Njc2OCIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSItMS4xOTIwOTI4OTU1MDc4MTI1ZS03IDAgMjA5LjI1MjM2NTExMjMwNDcgMjc2LjIwMzU1MjI0NjA5Mzc1IiBoZWlnaHQ9IjI3Ni4yMDM1NTIyNDYwOTM3NSIgd2lkdGg9IjIwOS4yNTIzNjUxMTIzMDQ3Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgkuc3Qwe2ZpbGw6IzU5ODZmMjt9CTwvc3R5bGU+CSYjeGE7ICA8ZyB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMS41MDc4NTk1LC05Ljc3OTM3ODMpIiBpZD0ibGF5ZXIxIj4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJtIDE2My41OTU1NywxMTYuMTQyMDIgNDcuMTY0NjUsMjguMDI0MzIgdiA0NC42MzY2NyBjIDAsNy45NjA3IC0zLjQyNjIxLDEyLjQwOTQ2IC05LjI0NTE1LDE2LjMyMzQ0IEwgNjcuMTkzNDY5LDI4NC4wNTE2IGMgLTUuNTE0MTUzLDMuNTg0IC05LjM3OTMyNSwxLjkyNjIxIC05LjM3OTMyNSwtMi44ODMwOSBWIDIzMy41NzM4OCBMIDE2My41OTU1NywxNzAuNzQ2MTEgWiBNIDYyLjYyMTM1Miw4Ny42ODQzMzkgViAzMS45MjQ2MSBMIDk1LjM0MDQ2NSwxMy4wMDA5NzMgYyA3LjUxNDMxNSwtNC42MDE4NzE3IDE1LjA5MjA3NSwtNC4wOTkzMDM2IDIxLjYwODQ0NSwwLjM5NzM5OSBsIDgxLjM4ODE1LDQ3LjEyODM4IGMgOS44NzAwNSw1LjYwNDA1OSAxMi4zNTYzOSwxMC41Nzc5MjggMTIuNDIzMTYsMjAuMDc5Mjc4IFYgMTI1LjQyMjIgTCAxMDUuNTk2NzgsNjMuMTI2OTQ1IFogTSA0Mi45MDMyMDgsMjI0LjA1MDEgMTMuMjg5ODgzLDIwNi44NTk5MiBDIDYuMTQyMjM5OCwyMDIuNDY5NTUgMS41MTY3ODAxLDE5OS43NTAxNyAxLjUxNjc4MDEsMTg3LjY0NzM3IFYgODMuNjM5NTkyIEMgMS4zOTg2OSw3NC4wOTg0NzkgMi4zMDMwNTY5LDY4LjUwMTMyOSAxMy40MzQzMzgsNjEuOTcxMzA0IEwgNDcuMjM2ODY3LDQyLjE4MDkzMyBWIDE3MS4xNzk0OCBsIDQzLjA0NzY2NiwyNC43MDE4NCB6Ii8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'contact center ai platform': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc2MjQ2IiB2ZXJzaW9uPSIxLjEiIHZpZXdCb3g9Ii0wLjAwMDAwMzgxNDY5NzI2NTYyNSAtMC4wMDAwMDM4MTQ2OTcyNjU2MjUgMTQyLjM2NTczNzkxNTAzOTA2IDE4NS40MDA0NTE2NjAxNTYyNSIgaGVpZ2h0PSIxODUuNDAwNDUxNjYwMTU2MjUiIHdpZHRoPSIxNDIuMzY1NzM3OTE1MDM5MDYiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojNDI4NWY0O30JLnN0MXtmaWxsOiNmZmZmZmY7fQk8L3N0eWxlPgkmI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTM3LjQ1MjcxMSwtNTUuMDE0ODM4KSIgaWQ9ImxheWVyMSI+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MCIgZD0iTSA3NS42NTQ0NzYsMjA0Ljc3MjcgNDUuMTMwNTE3LDE4Ni43OTU0IGMgLTUuODQwMzQ1LC0zLjMxMzMyIC03LjM5NjkxMiwtNS45MjE4NCAtNy4zOTY5MTIsLTEzLjk1MTE0IGwgLTAuMjgwODk0LC02Ny4yMjc2MiBjIDAsLTkuMzA5NTUgMi42NTc3MywtMTEuOTA5ODY4IDguODAxMzg3LC0xNS45MTczOTggTCAxMDIuODA3Nyw1Ni4zNjYzMjkgYyAyLjkzMjI5LC0xLjUzNTAwMSA4LjY2MjA2LC0yLjEyMTEzNyAxMi4xNzIxMiwwLjE4NzI2NCBsIDU2LjQ2NjYyLDMzLjM3ODM1MSBjIDYuNTQxMzYsMy42ODA5NTMgOC4zNzIwMSw2LjY5Mzg4MyA4LjM3MjAxLDE0Ljk4MTA4NiBsIC0wLjI4NzU1LDY4Ljk4MTE0IGMgLTAuMTcxNzEsNi4xMzYxNCAtMi4xOTk1NCw5LjgwODQyIC03LjExNjAxLDEyLjkwNzg4IGwgLTg5LjU1MDc2OCw1Mi4zMzM1MSBjIC0zLjk4NjEzMSwyLjczMDI0IC03LjAyMjM4MiwwLjgzODE3IC03LjAyMjM4MiwtMy4yNzcxMSB6Ii8+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MSIgZD0ibSA5OC41MDA2MjksMTc0LjkwNDE2IGEgMTAuMTEyMjMyLDEwLjExMjIzMiAwIDAgMSAtMTAuMTEyMjMyLDEwLjExMjIzIDEwLjExMjIzMiwxMC4xMTIyMzIgMCAwIDEgLTEwLjExMjIzMiwtMTAuMTEyMjMgMTAuMTEyMjMyLDEwLjExMjIzMiAwIDAgMSAxMC4xMTIyMzIsLTEwLjExMjIzIDEwLjExMjIzMiwxMC4xMTIyMzIgMCAwIDEgMTAuMTEyMjMyLDEwLjExMjIzIHogbSA2Mi41NDYwNDEsLTM1Ljk1NDYxIGEgMTAuMTEyMjMyLDEwLjExMjIzMiAwIDAgMSAtMTAuMTEyMjQsMTAuMTEyMjQgMTAuMTEyMjMyLDEwLjExMjIzMiAwIDAgMSAtMTAuMTEyMjMsLTEwLjExMjI0IDEwLjExMjIzMiwxMC4xMTIyMzIgMCAwIDEgMTAuMTEyMjMsLTEwLjExMjIzIDEwLjExMjIzMiwxMC4xMTIyMzIgMCAwIDEgMTAuMTEyMjQsMTAuMTEyMjMgeiBtIC0zMC4xNDk0NCwtMC4zNzQ1MiBhIDIxLjUzNTMwOSwyMS41MzUzMDkgMCAwIDEgLTIxLjUzNTMxLDIxLjUzNTMxIDIxLjUzNTMwOSwyMS41MzUzMDkgMCAwIDEgLTIxLjUzNTMwNiwtMjEuNTM1MzEgMjEuNTM1MzA5LDIxLjUzNTMwOSAwIDAgMSAyMS41MzUzMDYsLTIxLjUzNTMxIDIxLjUzNTMwOSwyMS41MzUzMDkgMCAwIDEgMjEuNTM1MzEsMjEuNTM1MzEgeiBNIDk4LjMxMzM2NiwxMDIuNjIwNDIgQSAxMC4xMTIyMzIsMTAuMTEyMjMyIDAgMCAxIDg4LjIwMTEzNCwxMTIuNzMyNjUgMTAuMTEyMjMyLDEwLjExMjIzMiAwIDAgMSA3OC4wODg5MDIsMTAyLjYyMDQyIDEwLjExMjIzMiwxMC4xMTIyMzIgMCAwIDEgODguMjAxMTM0LDkyLjUwODE5IDEwLjExMjIzMiwxMC4xMTIyMzIgMCAwIDEgOTguMzEzMzY2LDEwMi42MjA0MiBaIG0gNDYuNDQwNTQ0LDUxLjI0Mjg2IGEgNSw1IDAgMCAwIC0zLDIuMzc2OTUgYyAtNy45MzcwOCwxNC4yNTY2NiAtMTYuNzMzNDIsMTguNTQ2IC0zMy43NTE5NiwxOS41NzgxMyBhIDUsNSAwIDAgMCAtNC42ODc1LDUuMjk0OTIgNSw1IDAgMCAwIDUuMjkyOTcsNC42ODc1IGMgMTguODQyMDUsLTEuMTQyNzIgMzIuNjM3MzgsLTguMDg1MDUgNDEuODg0NzcsLTI0LjY5NTMxIGEgNSw1IDAgMCAwIC0xLjkzNzUsLTYuODAwNzggNSw1IDAgMCAwIC0zLjgwMDc4LC0wLjQ0MTQxIHogTSAxMDcuNzQyMTksOTIuMzYzMjgxIGEgNSw1IDAgMCAwIC00Ljg0NzY2LDUuMTQ2NDg1IDUsNSAwIDAgMCA1LjE0ODQ0LDQuODQ3NjU0IGMgMTYuMzA5NzgsLTAuNDg5OTEgMjQuNTAwMTYsNC44NjU4NSAzNC4xMDc0MiwxOC45NTExNyBhIDUsNSAwIDAgMCA2Ljk0OTIyLDEuMzE0NDYgNSw1IDAgMCAwIDEuMzEyNSwtNi45NDkyMiBDIDEzOS43NzU0MywxMDAuMDc5MjggMTI2Ljc0NDUzLDkxLjc5MjQ5MyAxMDcuNzQyMTksOTIuMzYzMjgxIFogTSA3Mi4wODAwNzgsMTEyLjI3NTM5IGEgNSw1IDAgMCAwIC0yLjkyNTc4MSwyLjQ2NjggYyAtOC42NzU5NzgsMTYuNzY0NzIgLTkuNzg0Nzk2LDMyLjE2NzM0IC0wLjI2MTcxOSw0OC42MjEwOSBhIDUsNSAwIDAgMCA2LjgzMjAzMSwxLjgyNDIyIDUsNSAwIDAgMCAxLjgyMjI2NiwtNi44MzIwMyBjIC04LjE3MzY5NSwtMTQuMTIyMzIgLTcuMzQ4MDQzLC0yMy44NzUzMyAwLjQ4ODI4MSwtMzkuMDE3NTggYSA1LDUgMCAwIDAgLTIuMTQyNTc4LC02LjczODI4IDUsNSAwIDAgMCAtMy44MTI1LC0wLjMyNDIyIHoiLz4mI3hhOyAgPC9nPiYjeGE7PC9zdmc+',
        'container- optimized os': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTEwIDBhMTAgMTAgMCAxIDAgMTAgMTBoMEExMCAxMCAwIDAgMCAxMCAwem0wIDE4YTggOCAwIDAgMS00LjE4LTEuMThsMy41OC0yLjA3aDB2LTQuNUw1LjUxIDh2NC41MmwyLjc1IDEuNTktMy40NiAyQTggOCAwIDAgMSA2LjA4IDN2NGgwTDEwIDkuMjggMTMuOSA3IDEwIDQuNzcgNy4yNCA2LjM2VjIuNDdhOCA4IDAgMCAxIDEwLjMxIDQuNyA4LjEgOC4xIDAgMCAxIC41MSAyLjgzdi4wN0wxNC40NiA4aDBsLTMuOSAyLjI2djQuNTFsMy45LTIuMjVWOS4zNGwzLjQ1IDJBOCA4IDAgMCAxIDEwIDE4eiIvPiYjeGE7PC9zdmc+',
        'container-optimized os': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTEwIDBhMTAgMTAgMCAxIDAgMTAgMTBoMEExMCAxMCAwIDAgMCAxMCAwem0wIDE4YTggOCAwIDAgMS00LjE4LTEuMThsMy41OC0yLjA3aDB2LTQuNUw1LjUxIDh2NC41MmwyLjc1IDEuNTktMy40NiAyQTggOCAwIDAgMSA2LjA4IDN2NGgwTDEwIDkuMjggMTMuOSA3IDEwIDQuNzcgNy4yNCA2LjM2VjIuNDdhOCA4IDAgMCAxIDEwLjMxIDQuNyA4LjEgOC4xIDAgMCAxIC41MSAyLjgzdi4wN0wxNC40NiA4aDBsLTMuOSAyLjI2djQuNTFsMy45LTIuMjVWOS4zNGwzLjQ1IDJBOCA4IDAgMCAxIDEwIDE4eiIvPiYjeGE7PC9zdmc+',
        'data catalog': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM3Ni4yNzQ4ODc3NTcyNjMyIiBoZWlnaHQ9IjMzOS42NzM1NDQyMTc3NjM4MyIgdmlld0JveD0iMC4xMTQwMDAwMDAwNTk2MDQ2NCAtMC4wOTAwMDAwMDM1NzYyNzg2OSA5OS41NTU5OTk3NTU4NTkzOCA4OS44NzE5OTQwMTg1NTQ2OSI+JiN4YTs8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qxe2ZpbGw6I2FlY2JmYTt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik03Ny41MjMgNDMuMzk3bDEyLjg0NCA3LjU3MnYxNC43NjdsLTEyLjg0NCA2LjY4ek01MC4zMTItLjA5bDEyLjg0NCA3LjU3MnYxNC43NjdsLTEyLjg0NCA2LjY4ek0yMy4xIDQzLjM5N2wxMi44NDQgNy41NzJ2MTQuNzY3TDIzLjEgNzIuNDE3em02OS40Ny0uNTExbDcuMS0xMS4xNjktMTIuNjY2LTIxLjU5NEg3MC42NDR2OS41aDEwLjkxOWw2Ljk3NyAxMS44OTUtNC4yNTYgNi42OTR6bS03Ni45NzktNC42TDExLjMgMzEuNDg1bDcuMjY0LTExLjg2MWg5Ljk3OWwuMDk5LTkuNUgxMy4yNDFMLjExNCAzMS41NjFsMS41NzYgMi40OTggNS41MTUgOC43Mzl6bTEzLjY2MiAzOS40NDlsNy42MDMgMTIuMDQ3aDI1LjkwMmw3LjczMy0xMi4xNjQtOC4xNDMtNC44OTktNC44MDggNy41NjRINDIuMDk1bC00Ljc0LTcuNTExeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik03Ny41MjMgNDMuMzk3bC0xMi44NDQgNy41NzJ2MTQuNzY3bDEyLjg0NCA2LjY4ek01MC4zMTItLjA5TDM3LjQ2OCA3LjQ4MnYxNC43NjdsMTIuODQ0IDYuNjh6TTIzLjEgNDMuMzk3bC0xMi44NDQgNy41NzJ2MTQuNzY3bDEyLjg0NCA2LjY4eiIvPiYjeGE7PC9zdmc+',
        'data labeling': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM3Ny42MDkwNzg2ODcyMTAwNiIgaGVpZ2h0PSIzMDYuMjk2NTE2MDQzNTQ3NzQiIHZpZXdCb3g9IjAuMDE5MDAwMDAxMjUxNjk3NTQgMC4yMzIwMDAwMDgyMjU0NDA5OCA5OS45MDkwMDQyMTE0MjU3OCA4MS4wNDEwMDAzNjYyMTA5NCI+JiN4YTs8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qxe2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0MntmaWxsOiM0Mjg1ZjQ7fSYjeGE7PC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMjUuMTgzLjIzMkw3LjM1MyAzNy4zNjYuMDQ4IDM3LjMzbC0uMDI5IDYgMjkuNDkyLjE0NmMxLjA4NiA2LjE1IDYuNDk5IDEwLjg3NiAxMi45NDQgMTAuODc2IDcuMjE4IDAgMTMuMTQ0LTUuOTI3IDEzLjE0NC0xMy4xNDRzLTUuOTI3LTEzLjE0NS0xMy4xNDQtMTMuMTQ1Yy01LjkyNCAwLTEwLjk3NiAzLjk5My0xMi41OTcgOS40MTVsLTEyLjU0NC0uMDYyTDMwLjg0NSA5LjIzMmgzMC4xMjl2LTlIMjUuMTgzem0xNy4yNzEgMzQuODNhNi4wOSA2LjA5IDAgMCAxIDYuMTQ1IDYuMTQ1IDYuMDkgNi4wOSAwIDAgMS02LjE0NSA2LjE0NGMtMi42MTYgMC00LjgwOS0xLjU3My01LjcwNi0zLjg0bDMuMjE0LjAxNi4wMjktNi0yLjQ3My0uMDEyYzEuMTEyLTEuNDk2IDIuODk2LTIuNDUzIDQuOTM2LTIuNDUzek0xNy44ODIgNDUuNzExbC04LjA4NiAzLjk1MSAxNS40NDEgMzEuNjExaDM1LjczNnYtOUgzMC44NThMMTcuODgyIDQ1LjcxMXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNNjAuOTc0IDgxLjI3M2gzOC45NTRWNjAuOTIyaC05LjAwM3YxMS4zNTJINjAuOTc0em0wLTcyLjA0MWgyOS45NTF2MTEuNzU1aDkuMDAzVi4yMzJINjAuOTc0eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik03NS43OTYgMjAuOTg3djguOTk5aDI0LjEzMnYtOC45OTl6TTYxLjExIDM1LjkyOHY5aDM4LjgxN3YtOXpNNzEuMjc0IDUxLjkxdjkuMDEyaDI4LjY1M1Y1MS45MXoiLz4mI3hhOzwvc3ZnPg==',
        'data loss prevention api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwLjAwMTcxNjYxMzc2OTUzIiBoZWlnaHQ9IjE0Ljc5ODEzMTk0Mjc0OTAyMyIgdmlld0JveD0iLTIuOTgwMjMyMjM4NzY5NTMxMmUtOCAtMC4wMDAxMzEyMzc1Mzg4ODA2Njg1OCAyMC4wMDE3MTY2MTM3Njk1MyAxNC43OTgxMzE5NDI3NDkwMjMiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTIuODYuODM4YTUuNDggNS40OCAwIDAgMC03LjA2IDEuMDYgNS4zMSA1LjMxIDAgMCAwLTEuMzQgMy42IDUuNDkgNS40OSAwIDAgMCAyLjQxIDQuNTNsLS4xNy4yOC0uNTYuMTYtMi4wNiAzLjQ4IDEuNDguODUgMi4wNS0zLjQ4LS4xNi0uNjEuMTQtLjI2YTUuNDkgNS40OSAwIDAgMCA1LjI3LTkuNjF6bS0xLjkyIDguM2EzLjc5IDMuNzkgMCAxIDEgMi42Ni00LjY1aDBhMy44IDMuOCAwIDAgMS0yLjY2IDQuNjV6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTS4wNSA0LjE3OGwuMTMtMS4wN2gxLjE4di4zNUguNTJ2LjQ1YS42OC42OCAwIDAgMSAuNzkuMTEuNzguNzggMCAwIDEgLjE3LjUzLjc3Ljc3IDAgMCAxLS4wOS4zNi41My41MyAwIDAgMS0uMjQuMjUuNjUuNjUgMCAwIDEtLjM4LjA5LjczLjczIDAgMCAxLS4zNi0uMDguNjYuNjYgMCAwIDEtLjI2LS4yMS42My42MyAwIDAgMS0uMTUtLjMyaC40MmEuMjcuMjcgMCAwIDAgLjA5LjIuMjUuMjUgMCAwIDAgLjIuMDcuMjMuMjMgMCAwIDAgLjIyLS4xLjQzLjQzIDAgMCAwIC4wNy0uMjkuMzcuMzcgMCAwIDAtLjA5LS4yNy4zMy4zMyAwIDAgMC0uMjUtLjEuNDEuNDEgMCAwIDAtLjI0LjA4aDB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTMuNDUgNS4yMThIM3YtMS42MWwtLjUxLjE1di0uMzZsLjg4LS4zMWgwek0xIDguMDU4SC41OXYtMS42MWwtLjUuMTV2LS4zNGwuOTEtLjMxaDB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTMuODYgNy4xODhhMS4xMyAxLjEzIDAgMCAxLS4xOC42Ny43NC43NCAwIDAgMS0xIDBoMGExIDEgMCAwIDEtLjE5LS42NXYtLjM5YTEuMDYgMS4wNiAwIDAgMSAuMTgtLjY3LjczLjczIDAgMCAxIDEgMGgwYTEuMDggMS4wOCAwIDAgMSAuMTkuNjV6bS0uNDItLjQzYS44My44MyAwIDAgMC0uMDctLjM2LjI1LjI1IDAgMCAwLS4yMy0uMTIuMjQuMjQgMCAwIDAtLjIyLjExLjc1Ljc1IDAgMCAwLS4wNy4zNnYuNTFhLjg1Ljg1IDAgMCAwIC4wNy4zOS4yMy4yMyAwIDAgMCAuMjMuMTIuMjMuMjMgMCAwIDAgLjIyLS4xMi43Ny43NyAwIDAgMCAuMDctLjM3eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0xNy4xMyA1LjEzOGgtLjQxdi0xLjYybC0uNTEuMTZ2LS4zNGwuODgtLjMyaDB6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE4LjYyIDQuMDk4bC4xMy0xLjA3aDEuMTh2LjM3aC0uODRsLS4wOS40M2EuNjUuNjUgMCAwIDEgLjMxLS4wOC42My42MyAwIDAgMSAuNDguMTkuNzQuNzQgMCAwIDEgLjE3LjUyLjgxLjgxIDAgMCAxLS4wOS4zNy42LjYgMCAwIDEtLjI1LjI1Ljc5Ljc5IDAgMCAxLS4zOC4wOS44NS44NSAwIDAgMS0uMzUtLjA4LjYyLjYyIDAgMCAxLS4yNi0uMjIuNTguNTggMCAwIDEtLjEtLjMySDE5YS4zNS4zNSAwIDAgMCAuMS4yMS4yOS4yOSAwIDAgMCAuMi4wNy4yNi4yNiAwIDAgMCAuMjItLjEuNDQuNDQgMCAwIDAgLjA2LS4zMy40MS40MSAwIDAgMC0uMDktLjI4LjM0LjM0IDAgMCAwLS4yNS0uMDkuMzQuMzQgMCAwIDAtLjI0LjA3aDB6bS0xLjA4IDMuMDlhMS4xMyAxLjEzIDAgMCAxLS4xOC42Ny43NC43NCAwIDAgMS0xIDBoMGExIDEgMCAwIDEtLjE5LS42NXYtLjM5YTEuMDYgMS4wNiAwIDAgMSAuMTgtLjY3LjczLjczIDAgMCAxIDEgMGgwYTEuMDggMS4wOCAwIDAgMSAuMTkuNjV6bS0uNDItLjQzYS44My44MyAwIDAgMC0uMDctLjM4LjI1LjI1IDAgMCAwLS4yMy0uMTIuMjQuMjQgMCAwIDAtLjIyLjExLjc1Ljc1IDAgMCAwLS4wNy4zNnYuNTFhLjg1Ljg1IDAgMCAwIC4wNy4zOS4yMy4yMyAwIDAgMCAuMjMuMTIuMjMuMjMgMCAwIDAgLjIyLS4xMi45LjkgMCAwIDAgLjA3LS4zN3oiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMTguNjIgNy4wMThsLjEzLTEuMDdoMS4xOHYuMzVoLS44NGwtLjA1LjQ1YS42NS42NSAwIDAgMSAuMzEtLjA4LjYzLjYzIDAgMCAxIC40OC4xOS43OC43OCAwIDAgMSAuMTcuNTQuNzcuNzcgMCAwIDEtLjA5LjM2LjUxLjUxIDAgMCAxLS4yNS4yNS42OS42OSAwIDAgMS0uMzguMDkuNzIuNzIgMCAwIDEtLjM1LS4wOC41OS41OSAwIDAgMS0uMjYtLjIxLjYzLjYzIDAgMCAxLS4xLS4zMkgxOWEuMzIuMzIgMCAwIDAgLjEuMi4yNS4yNSAwIDAgMCAuMi4wNy4yMy4yMyAwIDAgMCAuMjItLjEuNDMuNDMgMCAwIDAgLjA4LS4yOS4zNy4zNyAwIDAgMC0uMDktLjI3LjMxLjMxIDAgMCAwLS4yNS0uMS4zNS4zNSAwIDAgMC0uMjQuMDhoMHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNNy43MyA3LjUwOHYtLjk0YS44Ni44NiAwIDAgMSAuMzUtLjYyIDIuNDMgMi40MyAwIDAgMSAuODMtLjQzIDIuODcgMi44NyAwIDAgMSAyLjQyLjI4IDEuMDUgMS4wNSAwIDAgMSAuMjcuMi45LjkgMCAwIDEgLjMuNzV2Ljc2em0yLjA4LTIuNjFhMS4wOCAxLjA4IDAgMSAxIDEuMDgtMS4wN2gwYTEuMDkgMS4wOSAwIDAgMS0xLjA4IDEuMDd6Ii8+JiN4YTs8L3N2Zz4=',
        'data transfer': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmczNjAwOCIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSIwIDAgMTIxLjI1MDg3NzM4MDM3MTEgMTAwLjA2OTIyMTQ5NjU4MjAzIiBoZWlnaHQ9IjEwMC4wNjkyMjE0OTY1ODIwMyIgd2lkdGg9IjEyMS4yNTA4NzczODAzNzExIj4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgkuc3Qwe2ZpbGw6IzQyODVmNDt9CS5zdDF7ZmlsbDojYWVjYmZhO30JLnN0MntmaWxsOiM2NjlkZjY7fQk8L3N0eWxlPgkmI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTQ2LjIyMTU4LC05OC4zMzc4OCkiIGlkPSJsYXllcjEiPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDAiIGQ9Im0gNzkuNjMyOTE4LDE0Ni45MDY4OSA2Ljc2MTM0NSw2LjY3NDAxIC0xNC4xNjk0MiwxNC4yODQ0IGggNDcuMDI4OTA3IHYgOS41MDAyIEggNzIuMjI0ODQzIGwgMTQuMjA4NjkyLDE0LjMzNjU5IC02LjczMDMzOSw2LjcwNTAyIC0yNS41NjYzOTQsLTI1LjY2NDA3IHogbSA2Mi4zNDM0MzIsLTIzLjcxOTU4IC02Ljc2MTM1LDYuNjc0MDEgMTQuMTY5NDIsMTQuMjg0NCBoIC00Ny4wMjg5MSB2IDkuNTAwMTkgaCA0Ny4wMjg5MSBsIC0xNC4yMDg2OSwxNC4zMzY2IDYuNzMwMzMsNi43MDUwMiAyNS41NjY0LC0yNS42NjQwNyB6Ii8+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MSIgZD0ibSAxMDUuMzM1OTQsOTguMzM3ODkxIGMgLTExLjEyNjE1NywtMC4wMDg1IC0xOS43MDYxNTEsNC45OTk5MjkgLTI1LjQ3ODUxOCwxMS4xNTQyOTkgLTQuODYwMjQ5LDUuMTgxODkgLTcuODUwMDUzLDExLjAzNjc3IC05LjY2MDE1NiwxNS45OTIxOSAtNy45MTYyNCwxLjUyOTA1IC0xNC45NzI2NTksNS44MzI0NCAtMTkuMDk5NjEsMTIuMTAxNTYgbCAtMC4wODIwMywwLjEyNSAtMC4wNzQyMiwwLjEyODkgYyAtMy44NTQxNTcsNi43NDA3NCAtNS4wNjQ5NTksMTIuNDUwODYgLTQuNjM4NjcyLDE3LjI5MTAyIDAuMjM0MDk5LDIuNjU4MDIgMC44OTI4Nyw0Ljk0NSAxLjYyNTExOCw2Ljk0OTk5IGwgNy45ODk2ODcsLTYuNjU1NTggYyAtMC4wNjcxMiwtMC4zNzM1IC0wLjExODQ2OCwtMC43NDg2NSAtMC4xNTE5MTQsLTEuMTI4NCAtMC4yNDI0LC0yLjc1MjI5IDAuMjUzNjU4LC02LjExNTY3IDMuMzMwMDc4LC0xMS41NTY2NCAyLjgwMDQzMiwtNC4xODk2NSA4Ljg1Mjc1NiwtNy44NjkzMyAxNS4xMDM1MTYsLTguNDIxODcgbCAzLjIwODk4NCwtMC4yODMyIDAuOTIzODI4LC0zLjA4NTk0IGMgMS4yNTQ5ODEsLTQuMTkwMDIgNC4wNDA3NTksLTEwLjI1NDYyIDguNDUzMTI1LC0xNC45NTg5OSA0LjQxMjM2NiwtNC43MDQzNiAxMC4xNzYxMywtOC4xNTg3NSAxOC41NTA3ODQsLTguMTUyMzQgeiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDIiIGQ9Im0gMTA1LjMzNTk0LDk4LjMzNzg5MSB2IDkuNDk5OTk5IGMgOS40MDY5OSwwIDE2LjQ0NjI5LDMuNjYzNTIgMjMuNTY5MDUsMTMuOTMwMTEgbCA2Ljk5NDI4LC02LjUzNjQ1IEMgMTI3LjYwMjE4LDEwMy45Nzc4NiAxMTcuMTkzNzEsOTguMzM3ODkxIDEwNS4zMzU5NCw5OC4zMzc4OTEgWiIvPiYjeGE7ICA8L2c+JiN4YTs8L3N2Zz4=',
        'database migration service': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmcyMjQxOCIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSIwIDAgMTYzLjMzMzk2OTExNjIxMDk0IDE2My4xNDQ1NDY1MDg3ODkwNiIgaGVpZ2h0PSIxNjMuMTQ0NTQ2NTA4Nzg5MDYiIHdpZHRoPSIxNjMuMzMzOTY5MTE2MjEwOTQiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojYWVjYmZhO30JLnN0MXtmaWxsOiM2NjlkZjY7fQkuc3Qye2ZpbGw6IzQyODVmNDt9CTwvc3R5bGU+CSYjeGE7ICA8ZyB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMjQuMDIzMjA1LC02Ni45OTI5NjYpIiBpZD0ibGF5ZXIxIj4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJtIDI0LjAyMzIwNSwxMjIuMzc2NzMgdiAtMjAuOTczNTEgbCA1OS43MzY1MDEsMzMuODk0NyB2IDIxLjYyODk0IHogbSAwLDM2LjUxMzY0IHYgLTIxLjY4MTAzIGwgNTkuNzM2NTAxLDM0LjgxMjIgdiAyMS4zOTM0OCB6IG0gMCwzNi41MDMwOCB2IC0yMS42NTgzMSBsIDU5LjczNjUwMSwzNC43MjUyMiB2IDIxLjY3NzE0IHoiLz4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QxIiBkPSJNIDExMC4yMDQ2LDEwNS4xNDg0OCA4My43NTk3MDYsODkuNjIzNjI0IFYgNjYuOTkyOTY2IGwgNDYuMjAxMjA0LDI2LjYzODgxMiB6IG0gMzIuMTE1NywtMy42NTE2NCAyNC4xMTAxOCwwLjA5MzYgViA5MC4yNjEwMzQgbCAyMC45MjY3LDIwLjk3MzUxNiAtMjAuOTI2NywyMC45NzM1MiB2IC0xMS4zMjk0NSBoIC0yMC43Mzk0NCBsIC02MS45MzEzMzQsMzYuMDQ4MjQgdiAtMjEuNjI4OTQgeiBtIC01OC41NjA1OTQsOTEuOTE4MTggdiAtMjEuMzkzNDggbCA1OC43Nzk5OTQsLTM0LjEzMTMgMTcuMjUxOTMsMC4wNjgyIHYgMTkuNTY0MzMgbCAtMTQuMzQwNzQsLTAuMDQzNSB6IG0gNTguNTI2NTE0LC0xOC42NjIxIHYgMjEuNTg2MjYgTCA4My43NTk3MDYsMjMwLjEzNzUgdiAtMjEuNjc3MTQgeiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0gODMuNzU5NzA2LDY2Ljk5Mjk2NiBWIDg5LjYyMzYyNCBMIDQzLjkyOTM2NywxMTIuNjQ1NjkgMjQuMDIzMjA1LDEwMS40MDMyMiBaIi8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'dataflow': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE0LjUxOTk5OTUwNDA4OTM1NSIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDE0LjUxOTk5OTUwNDA4OTM1NSAyMCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGwtcnVsZTpldmVub2RkfSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0M3tmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPGcgY2xhc3M9InN0MCI+JiN4YTsJCTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik03LjM3IDIuMDNsLTEuNzIuOTYgMS41MiAxLjUtLjAyIDEuNzMgMS4wMi4wMS4wMi0xLjczIDQuMjQgMi41Ni0uMDEgMS4wNyAxLjc3LjAzVjYuMTFMOS4wNSAzLjA0bC0uMjctLjk0eiIvPiYjeGE7CQk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNNy4zNiAyLjAzbC0xLjQyLjM1LS4yOS42MUwuMzkgNS45Mi4zNiA3Ljk3IDIuMTQgOGwuMDItMS4wNyA0LjMxLTIuNDUtLjAyIDEuNzMuODYuMDEuMDYtNC4xOXoiLz4mI3hhOwkJPGcgY2xhc3M9InN0MSI+JiN4YTsJCQk8cGF0aCBkPSJNNy4zNiAyLjAzTDMuOTUgMCAyLjIxLjk1bDMuNDQgMi4wNCAxLjcyLS45NnptLjcxIDExLjc2bC0xLjcyLS4wMi0uMDIgMS43Mi44MiAyLjQ4IDEuNDItLjEyLjI5LS44NSA1LjI3LTIuOTMuMDMtMi4wOS0xLjc5LS4wMi0uMDIgMS4xLTQuMyAyLjQ1eiIvPiYjeGE7CQkJPHBhdGggZD0iTTcuMTUgMTcuOTdsLTMuNDYgMS45NGgtLjA1bC0xLjY2LS45OSAzLjQ5LTEuOTYgMS42OCAxLjAxeiIvPiYjeGE7CQk8L2c+JiN4YTsJCTxwYXRoIGNsYXNzPSJzdDMiIGQ9Ik0xMC44OC4wOWgtLjA1TDcuMzcgMi4wM2wxLjY4IDEuMDEgMy40OS0xLjk2ek0xMC42MiAyMGgtLjA1bC0zLjQyLTIuMDNoMCAwIDBsMS43Mi0uOTYgMy40NCAyLjA0eiIvPiYjeGE7CQk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNLjMzIDEzLjg5di0yaDEuNzZsLS4wMSAxLjA0IDQuMjUgMi41Ni4wMi0xLjcyLjg2LjAxLS4wNiA0LjE4LTEuNjgtMXoiLz4mI3hhOwk8L2c+JiN4YTsJPGNpcmNsZSBjbGFzcz0ic3QyIiBjeD0iMTMuMzgiIGN5PSIxMC4wNCIgcj0iMS4xNCIvPiYjeGE7CTxjaXJjbGUgY2xhc3M9InN0MiIgY3g9IjEuMTQiIGN5PSI5Ljg4IiByPSIxLjE0Ii8+JiN4YTsJPGNpcmNsZSBjbGFzcz0ic3QyIiBjeD0iNy4zMiIgY3k9IjcuOTkiIHI9IjEuMTQiLz4mI3hhOwk8Y2lyY2xlIGNsYXNzPSJzdDIiIGN4PSI3LjIzIiBjeT0iMTIiIHI9IjEuMTQiLz4mI3hhOzwvc3ZnPg==',
        'datalab': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjI3MS44OTgxMDE4MDY2NDA2IiBoZWlnaHQ9IjQyMy4wMDQwMjgzMjAzMTI1IiB2aWV3Qm94PSIwLjAwMDQ2MTI3MDM2MzMwMjkwMTQgMCAyNzEuODk4MTAxODA2NjQwNiA0MjMuMDA0MDI4MzIwMzEyNSI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDtmaWxsLXJ1bGU6ZXZlbm9kZH0mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xOTcuMzc4IDE0NC43NzRhMy4xMSAzLjExIDAgMCAxIDMuMTA1IDIuOTM0bC4wMDUuMTc3djE3LjEwN2EzLjExIDMuMTEgMCAwIDEtMi45MzQgMy4xMDVsLS4xNzcuMDA1aC0xMi40NDF2MzAuNjQ5YzAgMS4yMjcuMjk3IDIuNDM1Ljg2MiAzLjUyMmwuMTYxLjI5MyA4My44OTUgMTQ0LjI2MmExNS4yNiAxNS4yNiAwIDAgMSAuMTgyIDE0LjkzNmwtLjE4Mi4zMjQtMzAuNDMxIDUzLjI4NmExNS4yNiAxNS4yNiAwIDAgMS0xMi44NjEgNy42MjZsLS4zNTUuMDA0SDQ1LjY5MmExNS4yNiAxNS4yNiAwIDAgMS0xMy4wMzUtNy4zMjRsLS4xODEtLjMwNS0zMC40MzEtNTMuMjg2YTE1LjI2IDE1LjI2IDAgMCAxLS4xODItMTQuOTM2bC4xODItLjMyNCA4My42NzQtMTQ0LjI2MmMuNjIxLTEuMDc3IDEuMTYtMi4yODkgMS4yMzQtMy41MjhsLjAwOS0uMjg3di0zMC42NDlINzQuNTJjLTEuNjU4IDAtMy4wMTQtMS4yOTktMy4xMDUtMi45MzRsLS4wMDUtLjE3NnYtMTcuMTA3YTMuMTEgMy4xMSAwIDAgMSAyLjkzNC0zLjEwNWwuMTc2LS4wMDV6bS0zNS43NjkgMjMuMzI3aC01MS4zMnYzNS40MDVjMCAyLjUzMS0uNjI4IDUuMDE4LTEuODI2IDcuMjQybC0uMjE3LjM5TDI4LjAzMyAzNTAuOWE3LjYzIDcuNjMgMCAwIDAtLjEzOSA3LjM3NWwuMTQxLjI1NSAyMC43NDEgMzUuOTIxYTcuNjMgNy42MyAwIDAgMCA2LjMyNyAzLjgxbC4yODEuMDA1aDI1LjU3MmwtMjIuNjA1LTM5LjE1M2MtMS4zMTQtMi4yNzYtMS4zNjEtNS4wNjItLjE0MS03LjM3NWwuMTQxLS4yNTUgMTkuNjc5LTM0LjA4NmgxNDYuNjA2TDIxMi45ODggMjk3LjFoLTU0LjI1OWwtOC44MjEtMTUuMjc4aDU0LjMxMmwtMTYuMzMzLTI4LjQ2aC01NC43OGwtOC44MjEtMTUuMjc4aDU0LjgzM2wtMTUuNDY1LTI2Ljk0NmExNS4yNyAxNS4yNyAwIDAgMS0yLjAzOS03LjE4NWwtLjAwNy0uNDQ2em03Mi44NDQgMTY2LjQwMWwtNTQuMTgxLjAwMSA4LjgyMSAxNS41NTJoNTQuMjg1ek0xMDQuOTIxIDc5Ljc5NWM4LjQyNyAwIDE1LjI1OSA2LjgzMyAxNS4yNTkgMTUuMjYxcy02LjgzMiAxNS4yNTktMTUuMjU5IDE1LjI1OS0xNS4yNTktNi44MzItMTUuMjU5LTE1LjI1OSA2LjgzMi0xNS4yNjEgMTUuMjU5LTE1LjI2MXptNTcuNTc1LTMyLjc0M2MxMi42NDIgMCAyMi44OSAxMC4yNDcgMjIuODkgMjIuODg5cy0xMC4yNDkgMjIuODg5LTIyLjg5IDIyLjg4OS0yMi44ODktMTAuMjQ5LTIyLjg4OS0yMi44ODkgMTAuMjQ3LTIyLjg4OSAyMi44ODktMjIuODg5ek0xMjcuODEgMGM4LjQyNyAwIDE1LjI2MSA2LjgzMyAxNS4yNjEgMTUuMjYxUzEzNi4yMzcgMzAuNTIgMTI3LjgxIDMwLjUycy0xNS4yNTktNi44MzItMTUuMjU5LTE1LjI1OVMxMTkuMzg0IDAgMTI3LjgxIDB6Ii8+JiN4YTs8L3N2Zz4=',
        'dataplex': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmcxMTkyNDEiIHZlcnNpb249IjEuMSIgdmlld0JveD0iMC4wMDAwMDE5MDczNDg2MzI4MTI1IC00Ljc2ODM3MTU4MjAzMTI1ZS03IDI2NS4yMzA0Njg3NSAyODcuNzcxNDg0Mzc1IiBoZWlnaHQ9IjI4Ny43NzE0ODQzNzUiIHdpZHRoPSIyNjUuMjMwNDY4NzUiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojNTk4NmYyO30JLnN0MXtmaWxsOiNmZmZmZmY7fQk8L3N0eWxlPgkmI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoMjUuNTQ0OTIyLC01LjcxMjg5MDYpIiBpZD0ibGF5ZXIxIj4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJtIDIxMS4wMDM5MSwxODkuODczMDUgYyAtMTUuNzQwMzEsMCAtMjguNjgzNiwxMi45NDMyOSAtMjguNjgzNiwyOC42ODM1OSAwLDE1Ljc0MDMxIDEyLjk0MzI5LDI4LjY4MTY0IDI4LjY4MzYsMjguNjgxNjQgMTUuNzQwMywwIDI4LjY4MTY0LC0xMi45NDEzMyAyOC42ODE2NCwtMjguNjgxNjQgMCwtMTUuNzQwMyAtMTIuOTQxMzQsLTI4LjY4MzU5IC0yOC42ODE2NCwtMjguNjgzNTkgeiBNIDMuMDMzMjAzMSw1MS40NDkyMTkgYyAtMTUuNjgzMjA1MSwwIC0yOC41NzgxMjUxLDEyLjg5NDkyIC0yOC41NzgxMjUxLDI4LjU3ODEyNSA0ZS02LDE1LjY4MzIwMiAxMi44OTQ5MjMsMjguNTgwMDc2IDI4LjU3ODEyNTEsMjguNTgwMDc2IDE1LjY4MzIwMTksMCAyOC41ODAwNzM5LC0xMi44OTY4NzQgMjguNTgwMDc3OSwtMjguNTgwMDc2IDAsLTE1LjY4MzIwNSAtMTIuODk2ODczLC0yOC41NzgxMjUgLTI4LjU4MDA3NzksLTI4LjU3ODEyNSB6IE0gMTA3Ljc3MTQ4LDUuNzEyODkwNiA0NS41ODM5ODQsNDIuMzg2NzE5IDU3LjI2NzU3OCw2Mi4xOTkyMTkgOTYuNDQzMzU5LDM5LjA5NTcwMyBWIDEyOC4yNTM5MSBMIDI0LjkxOTkyMiw4MC4wMjczNDQgMTIuMDYwNTQ3LDk5LjA5NzY1NiA4Ni42NzU3ODEsMTQ5LjQwODIgMTMuOTk0MTQxLDE5OC4yMDExNyBWIDEzMi41OTU3IEggLTkuMDA1ODU5NCB2IDkwLjk1MzEzIGwgMTE3LjEwNTQ2OTQsNjkuOTM1NTQgNTkuNjc3NzMsLTM1Ljk3NDYgLTExLjg3NSwtMTkuNjk3MjcgLTM2LjQ1ODk4LDIxLjk3NjU2IHYgLTg4LjI4NzExIGwgNzAuMDA5NzYsNDcuMjA1MDggMTIuODU3NDMsLTE5LjA3MDMxIC03NC40MzE2NCwtNTAuMTg3NSA3My45MTAxNSwtNDkuNjE3MTg5IHYgNjYuNTgwMDc5IGggMjMgViA3NC45MTQwNjIgWiBtIDExLjY3MTg4LDMzLjYyMzA0NjQgNjkuNzUsNDEuMjQ4MDQ3IC02OS43NSw0Ni44MjYxNzYgeiBNIDk2LjQ0MzM1OSwxNzAuNTU0NjkgdiA4OS4xNzk2OCBMIDI2LjE0MjU3OCwyMTcuNzUgWiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDEiIGQ9Im0gMy4wMzMxOTc2LDY4LjQ0OTIxOSBjIDYuNDk1NzM2NywwIDExLjU4MDA4MzQsNS4wODIzOTMgMTEuNTgwMDgzNCwxMS41NzgxMjUgMCw2LjQ5NTczMSAtNS4wODQzNDY3LDExLjU4MDA3OCAtMTEuNTgwMDgzNCwxMS41ODAwNzggLTYuNDk1NzI2NywwIC0xMS41NzgxMjM0LC01LjA4NDM0NyAtMTEuNTc4MTIzNCwtMTEuNTgwMDc4IDAsLTYuNDk1NzMyIDUuMDgyMzk2NywtMTEuNTc4MTI1IDExLjU3ODEyMzQsLTExLjU3ODEyNSB6IE0gMjExLjAwMzkxLDIwNi44NzMwNSBjIDYuNTUyODMsMCAxMS42ODE2NCw1LjEzMDc2IDExLjY4MTY0LDExLjY4MzU5IDAsNi41NTI4MyAtNS4xMjg4MSwxMS42ODE2NCAtMTEuNjgxNjQsMTEuNjgxNjQgLTYuNTUyODQsMCAtMTEuNjgzNiwtNS4xMjg4MSAtMTEuNjgzNiwtMTEuNjgxNjQgMCwtNi41NTI4MyA1LjEzMDc2LC0xMS42ODM1OSAxMS42ODM2LC0xMS42ODM1OSB6IE0gMTA3Ljc2MzY3LDk4LjU1NDY4NyBjIC0yNy43NzI1NzgsM2UtNiAtNTAuNTIzNDMzLDIyLjc1MDg2MyAtNTAuNTIzNDMzLDUwLjUyMzQzMyAwLDI3Ljc3MjU4IDIyLjc1MDg1NSw1MC41MjE0OSA1MC41MjM0MzMsNTAuNTIxNDkgMjcuNzcyNTgsMCA1MC41MjM0NCwtMjIuNzQ4OTEgNTAuNTIzNDQsLTUwLjUyMTQ5IDAsLTI3Ljc3MjU3IC0yMi43NTA4NiwtNTAuNTIzNDM3IC01MC41MjM0NCwtNTAuNTIzNDMzIHoiLz4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJtIDEwNy43NjM2NywxMjAuNTU0NjkgYyAxNS44ODI5MSwtMTBlLTYgMjguNTIzNDQsMTIuNjQwNTMgMjguNTIzNDQsMjguNTIzNDMgMCwxNS44ODI5MSAtMTIuNjQwNTMsMjguNTIxNDkgLTI4LjUyMzQ0LDI4LjUyMTQ5IC0xNS44ODI5MDQsMCAtMjguNTIzNDM4LC0xMi42Mzg1OCAtMjguNTIzNDM4LC0yOC41MjE0OSAwLC0xNS44ODI5IDEyLjY0MDUzNCwtMjguNTIzNDMgMjguNTIzNDM4LC0yOC41MjM0MyB6Ii8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'dataprep by trifacta': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE4LjI3OTk5ODc3OTI5Njg3NSIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMS4yNDYyOTA4MDM4OTEyNzAxZS04IDAgMTguMjc5OTk4Nzc5Mjk2ODc1IDIwIj4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNjY5ZGY2O2ZpbGwtcnVsZTpldmVub2RkfSYjeGE7CS5zdDF7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qye2ZpbGwtcnVsZTpldmVub2RkfSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTcuNjMgOWEuOTEuOTEgMCAxIDEtLjY0My4yNjdBLjkxLjkxIDAgMCAxIDcuNjMgOXptMC0uOGExLjcxIDEuNzEgMCAxIDAgMS43IDEuNzEgMS43IDEuNyAwIDAgMC0xLjctMS43MXpNMS43MiA5YS45MS45MSAwIDEgMS0uNjQzLjI2N0EuOTEuOTEgMCAwIDEgMS43MiA5em0wLS44YTEuNzEgMS43MSAwIDEgMCAxLjcgMS43MSAxLjcgMS43IDAgMCAwLTEuNy0xLjcxem0zLjA0IDYuMTFhLjkxLjkxIDAgMSAxIDAgMS44Mi45MS45MSAwIDEgMSAwLTEuODJ6bTAtLjc5YTEuNzEgMS43MSAwIDEgMCAxLjIuNSAxLjcgMS43IDAgMCAwLTEuMi0uNXptMC05LjczYS45MS45MSAwIDAgMS0uMDQgMS44MTkuOTEuOTEgMCAwIDEtLjktLjkwOS45Mi45MiAwIDAgMSAuOTQtLjkxem0wLS44YTEuNzEgMS43MSAwIDEgMCAxLjIuNUExLjcgMS43IDAgMCAwIDQuNzYgM3oiLz4mI3hhOwk8ZyBjbGFzcz0ic3QxIj4mI3hhOwkJPHBhdGggZD0iTTcuODEgMGgxLjY4djIwSDcuODF6Ii8+JiN4YTsJCTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0xMy40IDIuODdIOC44OWEuMzcuMzcgMCAwIDAtLjMuNHYyLjgyYS4zNi4zNiAwIDAgMCAuMy4zOWg0LjUxYS4zNi4zNiAwIDAgMCAuMzEtLjM5VjMuMjhhLjM3LjM3IDAgMCAwLS4zMS0uNDF6bTQuMzIgNS4yOUg5LjRjLS4zMSAwLS41Ni4xOC0uNTYuMzl2Mi44MmMwIC4yMi4yNS40LjU2LjRoOC4zMmMuMzEgMCAuNTYtLjE5LjU2LS40VjguNTVjMC0uMjItLjI1LS4zOS0uNTYtLjM5em0tNS45MSA1LjI4SDguMjhjLS4xMyAwLS4yMy4xOC0uMjMuMzl2Mi44MmMwIC4yMi4xLjM5LjIzLjM5aDMuNTNjLjEzIDAgLjI0LS4xOC4yNC0uMzl2LTIuODJjLS4wMS0uMjItLjExLS4zOS0uMjQtLjM5eiIvPiYjeGE7CTwvZz4mI3hhOzwvc3ZnPg==',
        'dataproc': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE5LjM2MzAxMjMxMzg0Mjc3MyIgaGVpZ2h0PSIxNy45NzU1MjY4MDk2OTIzODMiIHZpZXdCb3g9IjAuMDAwNTYwMDI1NjI2MzI3ODQyNSAwLjYxOTYyOTc0MDcxNTAyNjkgMTkuMzYzMDEyMzEzODQyNzczIDE3Ljk3NTUyNjgwOTY5MjM4MyI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGwtcnVsZTpldmVub2RkO30mI3hhOwkuc3Qxe2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0MntmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDN7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxnIGNsYXNzPSJzdDAgc3QxIj4mI3hhOwkJPHBhdGggZD0iTTQuNjkgMTYuNGwxMC4xOS01Ljg5Ljk3IDEuNjktMTAuMTggNS44OHoiLz4mI3hhOwkJPHBhdGggZD0iTTcuNSA0LjR2MTAuMzVsLTEuODcgMS40MVY0LjR6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik0xNy40OSAxMS4ybC0uOTcgMS42OC04Ljk2LTUuMTktLjI2LTIuMzZ6Ii8+JiN4YTsJPC9nPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAgc3QyIiBkPSJNMTIuMzkgOC4yNkw3LjMgNS4zM2wuMjYgMi4zNiAxLjUxLjg2YTQgNCAwIDAgMCAzLjMyLS4yOXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIHN0MSIgZD0iTTYuMTMgNi4yOWgwYTMuNzggMy43OCAwIDAgMSA1LjE2NS01LjE2M0EzLjc4IDMuNzggMCAwIDEgOS40IDguMThhMy44IDMuOCAwIDAgMS0zLjI3LTEuODl6TTExIDMuNDlhMS44NCAxLjg0IDAgMCAwLTEuNTktLjkyQTEuODMgMS44MyAwIDAgMCA3LjU3IDQuNGExLjg0IDEuODQgMCAwIDAgMi43OTQgMS43MDZBMS44NCAxLjg0IDAgMCAwIDExLjI0IDQuNGExLjggMS44IDAgMCAwLS4yNC0uOTF6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCBzdDIiIGQ9Ik01LjYzIDEwLjk0djUuMjJsMS44Ny0xLjQxdi0xLjYzYTMuMjkgMy4yOSAwIDAgMC0xLjg3LTIuMTh6bTUuNyAzLjg3bDQuNTItMi42MS0yLjIxLTEtMS4yNS44YTQuMjMgNC4yMyAwIDAgMC0xLjA2IDIuODZ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCBzdDEiIGQ9Ik0uNTEgMTYuN2gwYTMuNzcgMy43NyAwIDAgMSAxLjM4LTUuMTYgMy43MiAzLjcyIDAgMCAxIDIuODYtLjM4QTMuNzggMy43OCAwIDEgMSAuNTEgMTYuN3ptNC44NS0yLjgxQTEuNzkgMS43OSAwIDAgMCA0LjI1IDEzYTEuODMgMS44MyAwIDAgMC0yLjA2IDIuNjloMGMuMzI5LjU2Ni45MzQuOTE0IDEuNTg5LjkxM2ExLjgzIDEuODMgMCAwIDAgMS41ODUtLjkyYy4zMjYtLjU2OC4zMjQtMS4yNjctLjAwNC0xLjgzM3ptNi45NyAyLjQ3aDBhMy43OSAzLjc5IDAgMCAxIDAtMy43NyAzLjc5IDMuNzkgMCAwIDEgNS4xNi0xLjM5IDMuNzggMy43OCAwIDAgMS0xLjg5IDcuMDQ0IDMuNzggMy43OCAwIDAgMS0zLjI3LTEuODg0em00Ljg2LTIuODFhMiAyIDAgMCAwLS42Ny0uNjcgMS44NSAxLjg1IDAgMCAwLTIuNTEuNjggMS44NiAxLjg2IDAgMCAwIDAgMS44MyAxLjgzIDEuODMgMCAwIDAgMi4wNy44NSAxLjgyIDEuODIgMCAwIDAgMS4xMS0uODUgMS44OCAxLjg4IDAgMCAwIDAtMS44NHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIHN0MyIgZD0iTTcuNDkgMTQuMTVsLTIuOCAyLjI1IDIuODYtMS42NWE0LjA3IDQuMDcgMCAwIDAtLjA2LS42ek04LjE1IDhsLS41OS0zLjZ2My4yOWEzLjQ3IDMuNDcgMCAwIDAgLjU5LjI3em01LjE1IDMuNDdsMy4yMiAxLjQxLTIuODYtMS42NGExLjY5IDEuNjkgMCAwIDAtLjM2LjIzeiIvPiYjeGE7PC9zdmc+',
        'datastore': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjMwIiBoZWlnaHQ9IjIxIiB2aWV3Qm94PSIwIDAgMzAgMjEiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0M3tmaWxsOiNmZmY7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggZD0iTTAgMGwxLjUgMS41aDZMOSAweiIgY2xhc3M9InN0MiIvPiYjeGE7CTxwYXRoIGQ9Ik05IDlWMEw3LjUgMS41djZ6IiBjbGFzcz0ic3QxIi8+JiN4YTsJPHBhdGggZD0iTTAgOWwxLjUtMS41di02TDAgMHoiIGNsYXNzPSJzdDIiLz4mI3hhOwk8cGF0aCBkPSJNOSA5TDcuNSA3LjVoLTZMMCA5eiIgY2xhc3M9InN0MCIvPiYjeGE7CTxwYXRoIGQ9Ik0xLjUgMS41aDZ2NmgtNnoiIGNsYXNzPSJzdDIiLz4mI3hhOwk8cGF0aCBkPSJNMTAuNSAwTDEyIDEuNWg2TDE5LjUgMHoiIGNsYXNzPSJzdDAiLz4mI3hhOwk8cGF0aCBkPSJNMTkuNSA5VjBMMTggMS41djZ6IiBjbGFzcz0ic3QxIi8+JiN4YTsJPHBhdGggZD0iTTEwLjUgOUwxMiA3LjV2LTZMMTAuNSAweiIgY2xhc3M9InN0MCIvPiYjeGE7CTxwYXRoIGQ9Ik0xOS41IDlMMTggNy41aC02TDEwLjUgOXoiIGNsYXNzPSJzdDEiLz4mI3hhOwk8cGF0aCBkPSJNMTIgMS41aDZ2NmgtNnoiIGNsYXNzPSJzdDMiLz4mI3hhOwk8cGF0aCBkPSJNMjEgMGwxLjUgMS41aDZMMzAgMHoiIGNsYXNzPSJzdDAiLz4mI3hhOwk8cGF0aCBkPSJNMzAgOVYwbC0xLjUgMS41djZ6IiBjbGFzcz0ic3QxIi8+JiN4YTsJPHBhdGggZD0iTTIxIDlsMS41LTEuNXYtNkwyMSAweiIgY2xhc3M9InN0MCIvPiYjeGE7CTxwYXRoIGQ9Ik0zMCA5bC0xLjUtMS41aC02TDIxIDl6IiBjbGFzcz0ic3QxIi8+JiN4YTsJPHBhdGggZD0iTTIyLjUgMS41aDZ2NmgtNnoiIGNsYXNzPSJzdDMiLz4mI3hhOwk8cGF0aCBkPSJNMCAxMmwxLjUgMS41aDZMOSAxMnoiIGNsYXNzPSJzdDAiLz4mI3hhOwk8cGF0aCBkPSJNOSAyMXYtOWwtMS41IDEuNXY2eiIgY2xhc3M9InN0MSIvPiYjeGE7CTxwYXRoIGQ9Ik0wIDIxbDEuNS0xLjV2LTZMMCAxMnoiIGNsYXNzPSJzdDAiLz4mI3hhOwk8cGF0aCBkPSJNOSAyMWwtMS41LTEuNWgtNkwwIDIxeiIgY2xhc3M9InN0MSIvPiYjeGE7CTxwYXRoIGQ9Ik0xLjUgMTMuNWg2djZoLTZ6IiBjbGFzcz0ic3QzIi8+JiN4YTsJPHBhdGggZD0iTTEwLjUgMTJsMS41IDEuNWg2bDEuNS0xLjV6IiBjbGFzcz0ic3QyIi8+JiN4YTsJPHBhdGggZD0iTTE5LjUgMjF2LTlMMTggMTMuNXY2eiIgY2xhc3M9InN0MSIvPiYjeGE7CTxwYXRoIGQ9Ik0xMC41IDIxbDEuNS0xLjV2LTZMMTAuNSAxMnoiIGNsYXNzPSJzdDIiLz4mI3hhOwk8cGF0aCBkPSJNMTkuNSAyMUwxOCAxOS41aC02TDEwLjUgMjF6IiBjbGFzcz0ic3QwIi8+JiN4YTsJPHBhdGggZD0iTTEyIDEzLjVoNnY2aC02em05LTEuNWwxLjUgMS41aDZMMzAgMTJ6IiBjbGFzcz0ic3QyIi8+JiN4YTsJPHBhdGggZD0iTTMwIDIxdi05bC0xLjUgMS41djZ6IiBjbGFzcz0ic3QxIi8+JiN4YTsJPHBhdGggZD0iTTIxIDIxbDEuNS0xLjV2LTZMMjEgMTJ6IiBjbGFzcz0ic3QyIi8+JiN4YTsJPHBhdGggZD0iTTMwIDIxbC0xLjUtMS41aC02TDIxIDIxeiIgY2xhc3M9InN0MCIvPiYjeGE7CTxwYXRoIGQ9Ik0yMi41IDEzLjVoNnY2aC02eiIgY2xhc3M9InN0MiIvPiYjeGE7PC9zdmc+',
        'datastream': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmczMjM0NyIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSIwIC0wLjAwMDAwMTkwNzM0ODYzMjgxMjUgMjY1LjgzODA3MzczMDQ2ODc1IDI0NS4zMDU1NTcyNTA5NzY1NiIgaGVpZ2h0PSIyNDUuMzA1NTU3MjUwOTc2NTYiIHdpZHRoPSIyNjUuODM4MDczNzMwNDY4NzUiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojMzM1YmJiO30JLnN0MXtmaWxsOiM3NjllZjU7fQk8L3N0eWxlPgkmI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoMjYuMDAxOTQ1LC0yNC45MTAzOTEpIiBpZD0ibGF5ZXIxIj4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJtIDQyLjE3OTY4NywzMy45Nzg1MTYgYyAtMC42NDE1MDMsMC4wMTg2IC0xLjI4NjQ4NywwLjAzODggLTEuOTM1MzIzLDAuMDU5OTIgMi4wMTg1ODUsOC44ODg3MiAyLjQ1ODk0MSwxNi40NTc5NjYgLTAuMDk3MzMsMjYuMDYyNzY0IDEyLjI5MTAzNywtMC4zNDA5NzUgMTkuMjU0OTQyLC0wLjQ0NTY3MyAyNi44NzQ0NDksMi45Mzc4NjYgbCAwLjAxOTUzLDAuMDA3OCAwLjAxOTUzLDAuMDA5OCBjIDYuMzEwNzgzLDIuNzc3OTA4IDE0LjMyNzI4NSwxMi42MDI0NyAyMS44NjcxODcsMjYuMTcxODc1IDcuNTM5OTAzLDEzLjU2OTM5OSAxNC43MTAwOCwyOS44NzM2NzkgMjQuMDc4MTMsNDMuNjQwNjE5IGwgMC4yOTEwMiwwLjQyNzczIDAuMzIyMjYsMC40MDIzNSBjIDkuODM1NCwxMi4yMzgxNSAyMy40ODA0MiwyMi43MDczNiA0OS4wODIzOCwyNi45Njg4MSAtMi4wODM5NiwtOS41MDI2NSAtMi4yMTQ2NywtMTYuMjA1NzYgLTAuMDQwOSwtMjYuMjk3OTIgLTE3LjE1OTg5LC0zLjAxOTUgLTIwLjk5MjI3LC03LjMxNTc2IC0yOC40MDg2NCwtMTYuNTMyMjQgQyAxMjcuMDIwNSwxMDcuMDkyODMgMTE5Ljg5NjEzLDkxLjQyODc1MiAxMTEuNjU2MjUsNzYuNTk5NjA5IDEwMy4zMjUyNyw2MS42MDY1MTYgOTMuOTU5MzUxLDQ2LjQ5OTg0MSA3Ny41NTI3MzQsMzkuMjY5NTMxIDY1LjMzNTEzMSwzMy44NDk2MzIgNTQuMzg3OTc1LDMzLjYyNDUwMyA0Mi4xNzk2ODcsMzMuOTc4NTE2IFogTSAyMzkuODM2MSwxNDcuMjkzNSBhIDI3LjU3ODE5NywyNy41NzgxOTcgMCAwIDEgLTI3LjU3ODIsMjcuNTc4MiAyNy41NzgxOTcsMjcuNTc4MTk3IDAgMCAxIC0yNy41NzgxOSwtMjcuNTc4MiAyNy41NzgxOTcsMjcuNTc4MTk3IDAgMCAxIDI3LjU3ODE5LC0yNy41NzgxOSAyNy41NzgxOTcsMjcuNTc4MTk3IDAgMCAxIDI3LjU3ODIsMjcuNTc4MTkgeiBNIDE4LjA0NjY0MSwyNDguMzU3ODggQSAyMS44NTgwNjEsMjEuODU4MDYxIDAgMCAxIC0zLjgxMTQxOTUsMjcwLjIxNTk0IDIxLjg1ODA2MSwyMS44NTgwNjEgMCAwIDEgLTI1LjY2OTQ4LDI0OC4zNTc4OCAyMS44NTgwNjEsMjEuODU4MDYxIDAgMCAxIC0zLjgxMTQxOTUsMjI2LjQ5OTgyIDIxLjg1ODA2MSwyMS44NTgwNjEgMCAwIDEgMTguMDQ2NjQxLDI0OC4zNTc4OCBaIE0gMTcuNzc4MjYzLDQ2Ljc2ODQ1MiBBIDIxLjg1ODA2MSwyMS44NTgwNjEgMCAwIDEgLTQuMDc5Nzk3Nyw2OC42MjY1MTMgMjEuODU4MDYxLDIxLjg1ODA2MSAwIDAgMSAtMjUuOTM3ODU5LDQ2Ljc2ODQ1MiAyMS44NTgwNjEsMjEuODU4MDYxIDAgMCAxIC00LjA3OTc5NzcsMjQuOTEwMzkxIDIxLjg1ODA2MSwyMS44NTgwNjEgMCAwIDEgMTcuNzc4MjYzLDQ2Ljc2ODQ1MiBaIE0gMTcuNzE0MTc2LDE0Ny42NTM3OSBBIDIxLjg1ODA2MSwyMS44NTgwNjEgMCAwIDEgLTQuMTQzODg0NywxNjkuNTExODUgMjEuODU4MDYxLDIxLjg1ODA2MSAwIDAgMSAtMjYuMDAxOTQ1LDE0Ny42NTM3OSAyMS44NTgwNjEsMjEuODU4MDYxIDAgMCAxIC00LjE0Mzg4NDcsMTI1Ljc5NTczIDIxLjg1ODA2MSwyMS44NTgwNjEgMCAwIDEgMTcuNzE0MTc2LDE0Ny42NTM3OSBaIi8+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MSIgZD0ibSAxMTIuOTc3MDgsMTY1LjM0MjcgYyAtNS4wNzQ2LDcuNjQ2MzQgLTkuMzI4NjcsMTQuNjczMTkgLTEyLjUxNDE5LDIwLjkxOTAyIGwgLTAuMTI1LDAuMjQ2MDkgLTAuMTE1MjMsMC4yNTE5NiBjIC05LjIxNTY3NiwyMC4xMzgwMSAtMTkuNTIyNDkxLDM2LjU4OTU2IC0yOS44MjgxMjksNDMuMzAwNzggLTEzLjE2MzE1Niw2Ljg2MzUzIC0xOS44OTkzNjgsNS41MTMwMSAtMzAuMzY0ODE1LDQuOTYxMDYgMy4xOTYwNDQsMTEuODA2MzMgMi40NDQ1MDYsMTkuMTEwMzEgMC4xNDI0NDgsMjYuMDUzMjEgOS41Nzc4NSwwLjUzMjM2IDI0LjkyODgzOSwxLjI3NDQyIDQyLjk1MDg4MywtOC4zMDcyNCBsIDAuNDI3NzM0LC0wLjIyNjU2IDAuNDEwMTU2LC0wLjI1OTc3IEMgMTAyLjgyMjMsMjQwLjM2NzggMTEzLjc4MTUyLDIxOS41Mzg5MSAxMjMuNjI1LDE5OC4wNzYxNyBjIDIuNjA2OTcsLTUuMTExNDYgNi42NzQ1MSwtMTEuODUxNSAxMS43MSwtMTkuMzk0ODQgLTkuMDc0NjgsLTMuMDc3OTUgLTE2Ljk0MDgxLC04LjYwOTg2IC0yMi4zNTc5MiwtMTMuMzM4NjMgeiBtIC03Mi44MTg1LC00LjYxNTM5IDQ2LjUxNDQ3MywwLjAxODEgOC45OTExNTgsLTEzLjI4MTQyIC04LjQxMzI4MiwtMTIuNzE4MzYgLTQ3LjA5MjQwNiwtMC4wMTgzIGMgMi44MTM0NzgsNy4zNjM5OCAyLjIyNDgyMiwxOS42MzkxMSA1LjdlLTUsMjYgeiIvPiYjeGE7ICA8L2c+JiN4YTs8L3N2Zz4=',
        'developer portal': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE0LjE0MzAxOTY3NjIwODQ5NiIgdmlld0JveD0iMCAwLjAwMDQ4OTk2NjI0NTM2ODEyMzEgMjAgMTQuMTQzMDE5Njc2MjA4NDk2Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qxe2ZpbGw6IzY2OWRmNjt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTAgMS40NzJhNS41OSA1LjU5IDAgMCAxIDQgMS42bDEtMWE3LjA3IDcuMDcgMCAwIDAtMTAgMGgwbDEgMWE1LjU5IDUuNTkgMCAwIDEgNC0xLjZ6bTAgMTEuMmE1LjU5IDUuNTkgMCAwIDEtNC0xLjZsLTEgMWE3LjA3IDcuMDcgMCAwIDAgMTAgMGgwbC0xLTFhNS41OSA1LjU5IDAgMCAxLTQgMS42eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xMCAxMC4xNDJhMy4wNiAzLjA2IDAgMCAxLTMtMi4zNEgzLjExdjIuMzhMMCA3LjA3MmwzLjExLTMuMXYyLjM4SDdhMy4wNiAzLjA2IDAgMCAxIDMtMi4zNGgwYTMuMDYgMy4wNiAwIDAgMSAzIDIuMzRoMy45MXYtMi4zOUwyMCA3LjA3MmwtMy4xMSAzLjEydi0yLjM5SDEzYTMuMDYgMy4wNiAwIDAgMS0zIDIuMzR6bTAtNC42OGExLjYxIDEuNjEgMCAxIDAgMS42MSAxLjYxaDBBMS42MSAxLjYxIDAgMCAwIDEwIDUuNDYyeiIvPiYjeGE7PC9zdmc+',
        'dialogflow enterprise edition': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE2LjAwMDAwNzYyOTM5NDUzIiBoZWlnaHQ9IjE5LjgzNjQ5NDQ0NTgwMDc4IiB2aWV3Qm94PSItMC4wMDAwMDY3MzA4MDY0ODk5NDA3MzMgMC4wMDAzMTcxNzE4ODUzOTkxNDc4NyAxNi4wMDAwMDc2MjkzOTQ1MyAxOS44MzY0OTQ0NDU4MDA3OCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTggOS45NzFsLTgtNHY2Ljc2YS40OS40OSAwIDAgMCAuMTkuMzlsNC42NCAyLjc1YS4zMi4zMiAwIDAgMSAuMTcuMjl2My41MWEuMTcuMTcgMCAwIDAgLjI2LjE0bDEwLjUxLTYuNjlhLjUuNSAwIDAgMCAuMjMtLjQydi02LjczeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik04IDcuOTcxbDgtNEw4LjEyLjAzMWEuMjUuMjUgMCAwIDAtLjI0IDBMMCAzLjk3MXoiLz4mI3hhOzwvc3ZnPg==',
        'distributed cloud': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTEwIDBhMTAgMTAgMCAxIDAgMTAgMTBoMEExMCAxMCAwIDAgMCAxMCAwem0wIDE4YTggOCAwIDAgMS00LjE4LTEuMThsMy41OC0yLjA3aDB2LTQuNUw1LjUxIDh2NC41MmwyLjc1IDEuNTktMy40NiAyQTggOCAwIDAgMSA2LjA4IDN2NGgwTDEwIDkuMjggMTMuOSA3IDEwIDQuNzcgNy4yNCA2LjM2VjIuNDdhOCA4IDAgMCAxIDEwLjMxIDQuNyA4LjEgOC4xIDAgMCAxIC41MSAyLjgzdi4wN0wxNC40NiA4aDBsLTMuOSAyLjI2djQuNTFsMy45LTIuMjVWOS4zNGwzLjQ1IDJBOCA4IDAgMCAxIDEwIDE4eiIvPiYjeGE7PC9zdmc+',
        'document ai': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmcyNDYzMyIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSItMi4zODQxODU3OTEwMTU2MjVlLTcgLTAuMDAwMDAxOTA3MzQ4NjMyODEyNSAyMDguNzEzMzQ4Mzg4NjcxODggMjU4Ljk2NjA5NDk3MDcwMzEiIGhlaWdodD0iMjU4Ljk2NjA5NDk3MDcwMzEiIHdpZHRoPSIyMDguNzEzMzQ4Mzg4NjcxODgiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojNTk4NmYyO30JPC9zdHlsZT4JJiN4YTsgIDxnIHRyYW5zZm9ybT0idHJhbnNsYXRlKC0zLjM5NDYyNDgsLTE3LjgxMDI4MikiIGlkPSJsYXllcjEiPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDAiIHRyYW5zZm9ybT0ic2NhbGUoMC4yNjQ1ODMzMykiIGQ9Im0gMTEyLjQ3MDcsNjcuMzE0NDUzIGMgLTU4LjMyOTU1MiwwIC05OS42NDA2MjIsNDEuMDM3NjQ3IC05OS42NDA2MjIsMTA2Ljg1MTU2NyB2IDc3NC4xODc1IGMgMCw1Ni4zMTM3OCA0My4yNjY1OTYsOTcuNzMwNDggMTAxLjI3NzM0Miw5Ny43MzA0OCBIIDQxMC4wOTk2MSBWIDk0Ny41MDU4NiBIIDEwOS4zODI4MSBWIDE2My4yMTg3NSBoIDMwMC43MTY4IFYgNjcuMzE0NDUzIFogbSA0NzEuNzIwNzEsMjguNzc3MzQ0IGEgNjkuODg0NDg5LDY5Ljg4NDQ4OSAwIDAgMCAtNjkuODg0NzcsNjkuODg0NzYzIDY5Ljg4NDQ4OSw2OS44ODQ0ODkgMCAwIDAgNDkuMDY0NDUsNjYuNzAxMTcgdiA3Ni44ODg2OCBjIDAsMzIuMTczNTQgLTMuMDAyNDksNTQuMjA4MzYgLTkuMDA1ODYsNjQuMzQ3NjUgLTYuMDAzMzYsMTAuMTM5MyAtMTQuMDEyNDIsMTUuMjk2ODggLTQyLjIzODI4LDE1LjI5Njg4IGggLTQ5LjE0MjU3IHYgMzkuOTk0MTQgaCA0OS4xNDI1NyBjIDM1LjMwNTEsMCA2Mi45MTM3NiwtMTEuNzEyNTIgNzYuNjUyMzUsLTM0LjkxNjAyIDEzLjczODU4LC0yMy4yMDM1NSAxNC41OTM3NSwtNTAuOTg3NjggMTQuNTkzNzUsLTg0LjcyMjY1IFYgMjMzLjEzNDc3IEEgNjkuODg0NDg5LDY5Ljg4NDQ4OSAwIDAgMCA2NTQuMDc0MjIsMTY1Ljk3NjU2IDY5Ljg4NDQ4OSw2OS44ODQ0ODkgMCAwIDAgNTg0LjE5MTQxLDk2LjA5MTc5NyBaIE0gMjA5LjEwNzQyLDM1OS43OTY4OCB2IDk2LjYzNjcxIGggMjAwLjkxNzk3IHYgLTk2LjYzNjcxIHogbSA1MjIuNjc3NzQsMjguNjkzMzUgYSA2OS44ODQ0ODksNjkuODg0NDg5IDAgMCAwIC02OS44ODQ3Nyw2OS44ODQ3NyA2OS44ODQ0ODksNjkuODg0NDg5IDAgMCAwIDQ0LjUzMzIsNjUuMTE5MTQgYyAtMC44MjI3MiwyOC4wMzEwNCAtOC4yMTYzLDQwLjA3MTk4IC0yMC44MTgzNiw0OC40NzY1NiAtMTMuMzg1NTMsOC45MjcxNyAtMzcuNzE0NzQsMTMuMzk4NDQgLTcxLjI3OTI5LDEzLjM5ODQ0IEggNDYzLjY2NDA2IHYgMzkuOTk0MTQgaCAxNTAuNjcxODggYyAzNi41Mjk0MywwIDY4LjI5MTkyLC0zLjMyNDIzIDkzLjQ2ODc1LC0yMC4xMTUyMyAyMy4zMjM0OCwtMTUuNTU0OTYgMzYuNjM5MTcsLTQyLjk3NzMxIDM4LjQ3NDYxLC03OC41NDEwMiBBIDY5Ljg4NDQ4OSw2OS44ODQ0ODkgMCAwIDAgODAxLjY2Nzk3LDQ1OC4zNzUgNjkuODg0NDg5LDY5Ljg4NDQ4OSAwIDAgMCA3MzEuNzg1MTYsMzg4LjQ5MDIzIFogTSAyMDkuMTA3NDIsNTU2LjQ4MjQyIHYgOTYuNjM2NzIgaCAyMDAuOTE3OTcgdiAtOTYuNjM2NzIgeiBtIDAsMTk2LjY4NzUgdiA5Ni42MzY3MiBoIDIwMC45MTc5NyB2IC05Ni42MzY3MiB6IG0gMjU0Ljk3NjU2LDI3LjU0Njg4IHYgMzkuOTk0MTQgaCA5OC41OTk2MSBjIDMyLjMxNDI1LDAgNTUuNDQ0MTIsMi41Mjc5NSA2Ni4yMzA0Nyw4LjAwMTk1IDUuMzkzMTYsMi43MzcwMiA4LjA4NDg4LDUuMzU1MzIgMTAuNTQyOTcsMTAuMjMyNDIgMi40NTgwOSw0Ljg3NzE0IDQuNDA2MjUsMTIuNzc3NjggNC40MDYyNSwyNS4wMzEyNSB2IDE5LjgxODM2IGEgNjkuODg0NDg5LDY5Ljg4NDQ4OSAwIDAgMCAtNDkuNzIyNjYsNjYuODk2NDkgNjkuODg0NDg5LDY5Ljg4NDQ4OSAwIDAgMCA2OS44ODQ3Nyw2OS44ODQ3OSA2OS44ODQ0ODksNjkuODg0NDg5IDAgMCAwIDY5Ljg4NDc3LC02OS44ODQ3OSA2OS44ODQ0ODksNjkuODg0NDg5IDAgMCAwIC01MC4wNDQ5MywtNjYuOTgyNDMgdiAtMTkuNzMyNDIgYyAwLC0xNi4zNjg4MyAtMi40NjIyLC0zMC42ODU1IC04LjY4NzUsLTQzLjAzNzExIC02LjIyNTI2LC0xMi4zNTE2MSAtMTYuNDkwMTcsLTIxLjk3MzAyIC0yOC4xNjIxMSwtMjcuODk2NDggQyA2MjMuNjcxNzUsNzgxLjE5NjA4IDU5Ni4yMTY3LDc4MC43MTY4IDU2Mi42ODM1OSw3ODAuNzE2OCBaIi8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'eventarc': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc4MzgiIHZlcnNpb249IjEuMSIgdmlld0JveD0iMCAwIDE2NC4zNDc1Nzk5NTYwNTQ3IDE2NC4zNDc1OTUyMTQ4NDM3NSIgaGVpZ2h0PSIxNjQuMzQ3NTk1MjE0ODQzNzUiIHdpZHRoPSIxNjQuMzQ3NTc5OTU2MDU0NyI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4JLnN0MHtmaWxsOiM0Mjg1ZjQ7fQkuc3Qxe2ZpbGw6IzY2OWRmNjt9CS5zdDJ7ZmlsbDojYWVjYmZhO30JPC9zdHlsZT4JJiN4YTsgIDxwYXRoIGNsYXNzPSJzdDAiIGQ9Im0gMTIzLjc3NzM4LDMzLjU0NDk0MiAtODkuODA4NjAxLDg5LjMyNjE2OCA4LjEwOTM3NSw4LjE1NDMgODkuODA4NTk2LC04OS4zMjYxNjcgeiBNIDE0LjUwODE5NywzNS41OTE3MzMgQyA1LjM2MTI1Miw0OC44Mzg2MTMgMCw2NC44OTExNTMgMCw4Mi4xNzM3OTMgYyAxZS02LDkuMjU1MzQgMS41NjA0MDEsMTguMTQ3NDM3IDQuMzkzNTMsMjYuNDU1MjI3IDMuMDY5ODYzLC0yLjQzNjk2IDYuNTEyODgzLC00LjM2MjU1IDEwLjE5NjI3NywtNS43MDI0OSAtMi4wMDQ5OTYsLTYuNTYwMjA3IC0zLjA4OTczMiwtMTMuNTI2NTY3IC0zLjA4OTczMiwtMjAuNzUyNzM3IDAsLTE0Ljk3MjQ3IDQuNjI5NjUsLTI4Ljg0MTI3IDEyLjUzODc3LC00MC4yNTYyMSB6IE0gNDEuNTA3NzQ1LDI0LjMyNDk2NiBjIDExLjQ5MjExMSwtOC4wODM0NzMgMjUuNTEzOTE5LC0xMi44MjQ4OTQgNDAuNjY2MDUxLC0xMi44MjQ4OTQgNy4yMjE5OSwwIDE0LjE4NjAxLDEuMDc5NzIyIDIwLjc0MjkyNCwzLjA4MjQ5OSAxLjM5MTExLC0zLjY4MTYwOCAzLjM2OTYsLTcuMTEzNDc0IDUuODU4NTUsLTEwLjE2MjE3IEMgMTAwLjQyODMzLDEuNTU3MzMyIDkxLjQ4MDA5NiwwIDgyLjE3Mzc5NiwwIDY0LjY3NjQzNywwIDQ4LjQzOTk0LDUuNDk1MjkyIDM1LjA5OTMyLDE0Ljg1MDg2MSBaIE0gMTIyLjc5MDM2LDE0MC4wNTc0IGMgLTExLjQ4Mjg2LDguMDYyMyAtMjUuNDg2MTc0LDEyLjc5MDEyIC00MC42MTY1NjQsMTIuNzkwMTEgLTcuMjg1MTg5LDAgLTE0LjMwNzk1LC0xLjA5ODU4IC0yMC45MTUwMDMsLTMuMTM1MjEgLTEuMzQ5NzksMy42Nzg3NiAtMy4yODQyNjIsNy4xMTU2NSAtNS43Mjg4NTEsMTAuMTc4MTkgOC4zNjE1MTYsMi44NzQyNiAxNy4zMTg1NTksNC40NTcwOSAyNi42NDM4NTQsNC40NTcxIDE3LjQ5NDc5LDAgMzMuNzI5MDk0LC01LjQ5MzY4IDQ3LjA2ODYwNCwtMTQuODQ2NzQgeiBtIDI3LjEzNDIyLC0xMS40MjUxNSBjIDkuMDk1MDMsLTEzLjIyMzA3IDE0LjQyMzAxLC0yOS4yMjk1MjcgMTQuNDIzMDEsLTQ2LjQ1ODQ1NyAwLC05LjI1NTQxIC0xLjUzOTE3LC0xOC4xNTcyIC00LjM3MjM0LC0yNi40NjUwNSAtMy4wNTEzMiwyLjQ4OTE4IC02LjQ4NjAyLDQuNDY3MTcgLTEwLjE3MDQ0LDUuODU3MDEgMS45NzY1Myw2LjUxNzY1IDMuMDQyNzEsMTMuNDM1MzggMy4wNDI3MSwyMC42MDgwNCAwLDE1LjA4ODE0IC00LjcwMTQ1LDI5LjA1NTQ3NyAtMTIuNzIyNjQsNDAuNTIwMjk3IHoiLz4mI3hhOyAgPHBhdGggY2xhc3M9InN0MSIgZD0iTSAxMDYuMDA3OCw4Mi42NDY3NjMgQSAyMy43NTg5NzYsMjMuNzU4OTc2IDAgMCAxIDgyLjI0ODgxNiwxMDYuNDA1NzQgMjMuNzU4OTc2LDIzLjc1ODk3NiAwIDAgMSA1OC40ODk4NCw4Mi42NDY3NjMgMjMuNzU4OTc2LDIzLjc1ODk3NiAwIDAgMSA4Mi4yNDg4MTYsNTguODg3NzgzIDIzLjc1ODk3NiwyMy43NTg5NzYgMCAwIDEgMTA2LjAwNzgsODIuNjQ2NzYzIFoiLz4mI3hhOyAgPHBhdGggY2xhc3M9InN0MiIgZD0ibSAxMzYuODc4OTQsMTE3LjEzNDc4IGMgLTExLjA1Nzc1LDAgLTIwLjE0NDU0LDkuMDg4NzQgLTIwLjE0NDUzLDIwLjE0NjQ5IDAsMTEuMDU3NzQgOS4wODY3OSwyMC4xNDQ1MyAyMC4xNDQ1MywyMC4xNDQ1MyAxMS4wNTc3MywwIDIwLjE0NjQ4LC05LjA4NjggMjAuMTQ2NDgsLTIwLjE0NDUzIDFlLTUsLTExLjA1Nzc0IC05LjA4ODc0LC0yMC4xNDY0OCAtMjAuMTQ2NDgsLTIwLjE0NjQ5IHogbSAwLDExLjUgYyA0Ljg0MjY4LDAgOC42NDY0OSwzLjgwMzggOC42NDY0OCw4LjY0NjQ5IDAsNC44NDI2OCAtMy44MDM4LDguNjQ0NTMgLTguNjQ2NDgsOC42NDQ1MyAtNC44NDI2OCwwIC04LjY0NDUzLC0zLjgwMTg1IC04LjY0NDUzLC04LjY0NDUzIDAsLTQuODQyNjkgMy44MDE4NCwtOC42NDY0OSA4LjY0NDUzLC04LjY0NjQ5IHogTSAyNy4wOTU3MzIsMTE2Ljk3NDYzIGMgLTExLjA1NzczNiwwIC0yMC4xNDQ1MjgsOS4wODY3OSAtMjAuMTQ0NTMxLDIwLjE0NDUzIC01ZS02LDExLjA1Nzc0IDkuMDg2NzksMjAuMTQ2NDggMjAuMTQ0NTMxLDIwLjE0NjQ4IDExLjA1Nzc0MiwwIDIwLjE0NjQ4OSwtOS4wODg3NCAyMC4xNDY0ODUsLTIwLjE0NjQ4IC0zZS02LC0xMS4wNTc3NCAtOS4wODg3NDgsLTIwLjE0NDUzIC0yMC4xNDY0ODUsLTIwLjE0NDUzIHogbSAwLDExLjUgYyA0Ljg0MjY4MiwwIDguNjQ2NDgzLDMuODAxODUgOC42NDY0ODUsOC42NDQ1MyAyZS02LDQuODQyNjggLTMuODAzOCw4LjY0NjQ4IC04LjY0NjQ4NSw4LjY0NjQ4IC00Ljg0MjY4NCwwIC04LjY0NDUzMywtMy44MDM4IC04LjY0NDUzMSwtOC42NDY0OCAxMGUtNywtNC44NDI2OCAzLjgwMTg0OSwtOC42NDQ1MyA4LjY0NDUzMSwtOC42NDQ1MyB6IE0gMTM2Ljk0MTQ0LDcuMzQzNzcgYyAtMTEuMDU3NzQsM2UtNiAtMjAuMTQ2NDksOS4wODY3OTUgLTIwLjE0NjQ5LDIwLjE0NDUzMSAwLDExLjA1Nzc0MiA5LjA4ODc1LDIwLjE0NjQ4MiAyMC4xNDY0OSwyMC4xNDY0ODIgMTEuMDU3NzQsMWUtNSAyMC4xNDQ1MywtOS4wODg3NCAyMC4xNDQ1MywtMjAuMTQ2NDgyIDAsLTExLjA1Nzc0MSAtOS4wODY3OSwtMjAuMTQ0NTM2IC0yMC4xNDQ1MywtMjAuMTQ0NTMxIHogbSAwLDExLjUgYyA0Ljg0MjY4LC0yZS02IDguNjQ0NTMsMy44MDE4NDcgOC42NDQ1Myw4LjY0NDUzMSAwLDQuODQyNjg1IC0zLjgwMTg1LDguNjQ2NDgyIC04LjY0NDUzLDguNjQ2NDgyIC00Ljg0MjY4LDAgLTguNjQ2NDksLTMuODAzNzk5IC04LjY0NjQ5LC04LjY0NjQ4MiAwLC00Ljg0MjY4MiAzLjgwMzgxLC04LjY0NDUzIDguNjQ2NDksLTguNjQ0NTMxIHogTSAyNy4wODk4NzMsNy40Mzc1MiBjIC0xMS4wNTc3MzksLTFlLTYgLTIwLjE0NDUzMSw5LjA4Njc5MiAtMjAuMTQ0NTMxLDIwLjE0NDUzMSAyZS02LDExLjA1Nzc0MiA5LjA4Njc5NCwyMC4xNDQ1MzIgMjAuMTQ0NTMxLDIwLjE0NDUzMiAxMS4wNTc3MzYsMCAyMC4xNDY0ODIsLTkuMDg2OCAyMC4xNDY0ODQsLTIwLjE0NDUzMiAwLC0xMS4wNTc3MzggLTkuMDg4NzQ2LC0yMC4xNDQ1MzEgLTIwLjE0NjQ4NCwtMjAuMTQ0NTMxIHogbSAwLDExLjUgYyA0Ljg0MjY4MywwIDguNjQ2NDg0LDMuODAxODQ4IDguNjQ2NDg0LDguNjQ0NTMxIC0xMGUtNyw0Ljg0MjY4MiAtMy44MDM4MDIsOC42NDQ1MzIgLTguNjQ2NDg0LDguNjQ0NTMyIC00Ljg0MjY4MywwIC04LjY0NDUzLC0zLjgwMTg0OSAtOC42NDQ1MzEsLTguNjQ0NTMyIDAsLTQuODQyNjgzIDMuODAxODQ4LC04LjY0NDUzMSA4LjY0NDUzMSwtOC42NDQ1MzEgeiIvPiYjeGE7PC9zdmc+',
        'filestore': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE2IiB2aWV3Qm94PSIwIDAgMjAgMTYiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTIgMTBIOEw2IDhoOHoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMTYgMkg0bDEtMmgxMHptMyAzSDFsMS0yaDE2eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xNCA3bC0yIDNIOEw2IDdIMHY5aDIwVjd6Ii8+JiN4YTs8L3N2Zz4=',
        'firestore': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjMyMy45MDU2MTAzOTg2NzUxNSIgaGVpZ2h0PSIzNzYuNDIyMjk0OTYzNjg0MDciIHZpZXdCb3g9Ii0wLjA5NzAwMDAwMjg2MTAyMjk1IDAuMjg3OTk5OTg3NjAyMjMzOSA4NS42OTk5OTY5NDgyNDIxOSA5OS41OTUwMDEyMjA3MDMxMiI+JiN4YTs8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojYWVjYmZhO30mI3hhOwkuc3Qxe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MntmaWxsOiM0Mjg1ZjQ7fSYjeGE7PC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNLS4wOTcgNzUuODE1VjU1Ljg3NGw0Mi44NS0yMC4xODN2MTkuMDd6bTAtMzUuNDAzVjIwLjQ3MUw0Mi43NTMuMjg4djE5LjA3eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik04NS42MDMgNzUuODE1VjU1Ljg3NGwtNDIuODUtMjAuMTgzdjE5LjA3em0wLTM1LjQwM1YyMC40NzFMNDIuNzUzLjI4OHYxOS4wN3oiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNNDIuNzUzIDgwLjMxNGwxNi4yMTctNy41MjUgMjEuMDg0IDkuNzE3LTM3LjMwMSAxNy4zNzd6Ii8+JiN4YTs8L3N2Zz4=',
        'gke on-prem': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjQwMi4zNDMyMDA2ODM1OTM3NSIgaGVpZ2h0PSI0MTYuMDAyNTMyOTU4OTg0NCIgdmlld0JveD0iMCAwLjAwMDQ5OTk2Mzc2MDM3NTk3NjYgNDAyLjM0MzIwMDY4MzU5Mzc1IDQxNi4wMDI1MzI5NTg5ODQ0Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qxe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MntmaWxsOiNhZWNiZmE7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTM2Ni4xNyA5Mi4wMDNjLTE5LjA1IDAtMzYgMTYuODItMzYgMzUuNzYgMCAxMi42MiA4LjQ2IDI1LjI0IDE5LjA1IDMxLjU1djE0Ny4zbC0xMTAuMDUgNjUuMjEgMTYuOTMgMjcuMzUgMTE4LjUxLTY5LjQyYzQuMjQtMi4xIDguNDctOC40MSA4LjQ3LTE0Ljczdi0xNTUuNjdjMTIuNzEtNi4zNSAxOS4wOS0xOC45MyAxOS4wOS0zMS41NSAyLjA4LTE4Ljk0LTE0Ljg1LTM1LjgtMzYtMzUuOHptLTM4LjExLTIzLjFMMjA5LjU1IDEuNTgzYy00LjI0LTIuMTEtMTAuNTktMi4xMS0xNi45MyAwTDU3LjE3IDc5LjQxM0EzNiAzNiAwIDAgMCAzNiA3My4xMDNjLTE5IDAtMzYgMTYuODMtMzYgMzUuNzZzMTYuOTMgMzUuNzcgMzYgMzUuNzcgMzYtMTYuODMgMzYtMzUuNzdsMTI5LjEtNzMuNjIgMTEwIDYzLjExem0tMTQzLjg5IDI3Ny42OHEtOS41MyAwLTE5IDYuMzFsLTExMC02My4xMXYtMTI2LjIyaC0zNHYxMzQuNjNjMCA2LjMyIDQuMjMgMTIuNjMgOC40NiAxNC43M2wxMTguNTQgNjUuMjF2Mi4xMWMwIDE4LjkzIDE2LjkzIDM1Ljc2IDM2IDM1Ljc2czM2LTE2LjgzIDM2LTM1Ljc2LTE3LTMzLjY2LTM2LTMzLjY2eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik05Ny4zOCAxMzYuMjEzbDEwNS44MiA1OC45MSAxMDMuNy01OC45MS0xMDMuNy02MXptLTYuMzUgNjcuMzJsMTEyLjE3IDYzLjExdi01MC40OWwtMTEyLjE3LTY1LjIxem0wIDYzLjExbDExMi4xNyA2NS4yMXYtNDQuMTdsLTExMi4xNy02NS4yMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMjAzLjE3IDIxNi4xMjN2NTAuNTZsMTEyLjE2LTY1LjI5di01MC4zOXptOTItMjBhOC4xNiA4LjE2IDAgMSAxIDguMTYtOC4xNiA4LjE5IDguMTkgMCAwIDEtOC4xNiA4LjE2em0tOTIgOTEuNTJ2NDQuMTZsMTEyLjE2LTY1LjEydi00NC4xNnptOTItMjIuODhhOC4xNiA4LjE2IDAgMSAxIDguMTYtOC4xNiA4LjE5IDguMTkgMCAwIDEtOC4xNiA4LjE2eiIvPiYjeGE7PC9zdmc+',
        'google cloud vmware engine': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc2NDI3IiB2ZXJzaW9uPSIxLjEiIHZpZXdCb3g9Ii0wLjAwMDAwNzYyOTM5NDUzMTI1IC0wLjAwMDAwNzYyOTM5NDUzMTI1IDEzOS4zMzEyMzc3OTI5Njg3NSAxMzkuNTE4MDIwNjI5ODgyOCIgaGVpZ2h0PSIxMzkuNTE4MDIwNjI5ODgyOCIgd2lkdGg9IjEzOS4zMzEyMzc3OTI5Njg3NSI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4JLnN0MHtmaWxsOiM0Mjg1ZjQ7fQkuc3Qxe2ZpbGw6I2ZmZmZmZjt9CTwvc3R5bGU+CSYjeGE7ICA8ZyB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMzcuNjMyODE2LC02MC42NzMzOTIpIiBpZD0ibGF5ZXIxIj4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJtIDY1LjI2MTM0OSw4OS40MTgzNDUgMjguNjUxMzI0LDJlLTYgLTAuMTg3MjYzLC0yOC43NDQ5NTUgaCA4My4wNTEzOSBsIDAuMTg3MjYsODMuMTQ1MDE4IC0yOC41NTc3LDAuMDkzNiB2IDI4LjU1NzcgSCA2NS40NDg2MTIgWiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDEiIGQ9Im0gNzIuODQ1Njk4LDEyOS43Njc1OCBjIC0xOS40MDU0NjEsMCAtMzUuMjEyODgyLDE1LjgwNTQ3IC0zNS4yMTI4ODIsMzUuMjEwOTQgMCwxOS40MDU0NiAxNS44MDc0MjEsMzUuMjEyODkgMzUuMjEyODgyLDM1LjIxMjg5IDE5LjQwNTQ2OCwwIDM1LjIxMDk0MiwtMTUuODA3NDMgMzUuMjEwOTQyLC0zNS4yMTI4OSAwLC0xOS40MDU0NyAtMTUuODA1NDc0LC0zNS4yMTA5NCAtMzUuMjEwOTQyLC0zNS4yMTA5NCB6IE0gMTA1Ljg5MDYzLDcyLjk3ODUxNiBWIDEwMS41MzUxNiBIIDc3LjIzODI4NSB2IDYgNTMuMjM4MjggaCA1OC44MTY0MDUgdiAtMjguODM3ODkgaCAyOC45NDMzNiBsIC0wLjExNzE5LC01OC45NTcwMzQgeiBtIDEyLDEyIGggMzUuMDEzNjcgbCAwLjA3MDMsMzQuOTU3MDM0IGggLTI4LjkxOTkyIHYgMjguODM3ODkgSCA4OS4yMzgyNzkgdiAtMzUuMjM4MjggaCAyOC42NTIzNTEgeiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDAiIGQ9Im0gNzIuODQ1NzAzLDEzNi43Njc1OCBjIDE1LjYyMjM4OCwwIDI4LjIxMDkzNywxMi41ODg1NSAyOC4yMTA5MzcsMjguMjEwOTQgMCwxNS42MjIzOCAtMTIuNTg4NTQ5LDI4LjIxMjg5IC0yOC4yMTA5MzcsMjguMjEyODkgLTE1LjYyMjM4NywwIC0yOC4yMTI4OTEsLTEyLjU5MDUxIC0yOC4yMTI4OTEsLTI4LjIxMjg5IDAsLTE1LjYyMjM5IDEyLjU5MDUwNCwtMjguMjEwOTQgMjguMjEyODkxLC0yOC4yMTA5NCB6Ii8+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MSIgZD0ibSA3Mi41MTk1MzEsMTQ4Ljg3NSAtNC40ODA0NjksNC40Mjk2OSA5LjA5NTcwNCw5LjIwMzEyIEggNTYuNjg1NTQ3IHYgNi4yOTg4MyBoIDIwLjQyMTg3NSBsIC05LjA2MjUsOS4xMjEwOSA0LjQ2ODc1LDQuNDM5NDYgMTYuNTk3NjU2LC0xNi43MDMxMyB6Ii8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'google data studio': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmcxMDczNDEiIHZlcnNpb249IjEuMSIgdmlld0JveD0iMCAwIDI3NS45ODY2OTQzMzU5Mzc1IDI1Mi40Mjk1MzQ5MTIxMDkzOCIgaGVpZ2h0PSIyNTIuNDI5NTM0OTEyMTA5MzgiIHdpZHRoPSIyNzUuOTg2Njk0MzM1OTM3NSI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4JLnN0MHtmaWxsOiM3NjllZjU7fQkuc3Qxe2ZpbGw6IzQwNzVlNjt9CTwvc3R5bGU+CSYjeGE7ICA8ZyB0cmFuc2Zvcm09InRyYW5zbGF0ZSgzMi40NTE1MzMsLTIwLjk0NjAxKSIgaWQ9ImxheWVyMSI+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MCIgZD0ibSAxMDEuNjgwMDksMjczLjM3NTU0IGMgLTE2LjQ1MjEyLDAgLTMwLjkxMzQyMiwtMTQuMTc3MzIgLTMwLjkxMzQyMiwtMzQuMjM1OSAwLC0xOS4xNzQ5OSAxNS4xNTE1MjIsLTMzLjY1ODA3IDMzLjUxMzYxMiwtMzMuNjU4MDcgaCAxMDQuODc0NTEgdiA2Ny44OTM5NyB6IE0gLTEuNTM4MTA0NiwxODEuODUzMzYgYyAtMTYuNDUyMTI2NCwwIC0zMC45MTM0Mjg0LC0xNC4xNzczMiAtMzAuOTEzNDI4NCwtMzQuMjM1ODkgMCwtMTkuMTc1IDE1LjE1MTUxOSwtMzMuNjU4MDggMzMuNTEzNjE4NCwtMzMuNjU4MDggSCAxMDUuOTM2NiB2IDY3Ljg5Mzk3IHogTSAxMDEuNjgwMSw4OC44Mzk5OCBjIC0xNi40NTIxMzEsMCAtMzAuOTEzNDMzLC0xNC4xNzczMTcgLTMwLjkxMzQzMywtMzQuMjM1ODk1IDAsLTE5LjE3NDk5NCAxNS4xNTE1MTksLTMzLjY1ODA3NSAzMy41MTM2MjMsLTMzLjY1ODA3NSBIIDIwOS4xNTQ4IHYgNjcuODkzOTcgeiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDEiIGQ9Im0gMjQzLjUzNTE1LDIzOS40Mjg1NSBjIDAsMTguOTg3NzUgLTE1LjM5MjYxLDMzLjk0Njk5IC0zNC4zODAzNiwzMy45NDY5OSAtMTguOTg3NzQsMCAtMzQuMzgwMzQsLTE0Ljk1OTI0IC0zNC4zODAzNCwtMzMuOTQ2OTkgMCwtMTguOTg3NzQgMTUuMzkyNiwtMzMuOTQ2OTggMzQuMzgwMzQsLTMzLjk0Njk4IDE4Ljk4Nzc1LC0xZS01IDM0LjM4MDM2LDE0Ljk1OTI0IDM0LjM4MDM2LDMzLjk0Njk4IHogTSAxNDAuMzE2OTYsMTQ3LjkwNjM4IGMgMCwxOC45ODc3NCAtMTUuMzkyNjEsMzMuOTQ2OTkgLTM0LjM4MDM2LDMzLjk0Njk4IC0xOC45ODc3NDUsMCAtMzQuMzgwMzU1LC0xNC45NTkyNCAtMzQuMzgwMzU1LC0zMy45NDY5OCAwLC0xOC45ODc3NSAxNS4zOTI2MSwtMzMuOTQ2OTkgMzQuMzgwMzU1LC0zMy45NDY5OSAxOC45ODc3NSwwIDM0LjM4MDM2LDE0Ljk1OTI0IDM0LjM4MDM2LDMzLjk0Njk5IHogTSAyNDMuNTM1MTUsNTQuODkyOTk0IGMgMCwxOC45ODc3NDcgLTE1LjM5MjYxLDMzLjk0Njk5IC0zNC4zODAzNiwzMy45NDY5ODYgLTE4Ljk4Nzc0LC0xMGUtNyAtMzQuMzgwMzQsLTE0Ljk1OTI0MyAtMzQuMzgwMzQsLTMzLjk0Njk4NiAwLC0xOC45ODc3NDMgMTUuMzkyNiwtMzMuOTQ2OTgzIDM0LjM4MDM0LC0zMy45NDY5ODQgMTguOTg3NzUsLTVlLTYgMzQuMzgwMzYsMTQuOTU5MjM3IDM0LjM4MDM2LDMzLjk0Njk4NCB6Ii8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'google kubernetes engine': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjMyOS45MjU5OTcyMzE3OTM4IiBoZWlnaHQ9IjM3OC4yODQ5OTAzMTEyNzg4IiB2aWV3Qm94PSIwIDAgODcuMjkyOTk5MjY3NTc4MTIgMTAwLjA4Nzk5NzQzNjUyMzQ0Ij4mI3hhOzxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiNhZWNiZmE7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6IzQyODVmNDt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik00My43NTEgMEwwIDI1LjQ2NXYyLjU4OCA0Ni45Mmw0My43NTIgMjUuMTE1IDQzLjU0MS0yNS4xMjFWMjUuNDczem0yLjQzOCAxMS44NTNsMzIuMTAzIDE4Ljc4MlY2OS43N0w0My43MzkgODkuNzA1IDkgNjkuNzYyVjMwLjY0MWwzMi4xOS0xOC43MzZ2MTQuMTU0TDI0LjUwMyAzNi4xNTNsMTkuMTcyIDExLjUwMiAxOC44ODYtMTEuNTU0LTE2LjM3Mi0xMC4wMjR6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTIyLjAyNSA0MC40OTZsLjE2NiAxOS4xNDMtMTMuMjQ3IDcuMzN2Mi43NDJsMi42MzcgMS41MTQgMTIuNjQ4LTYuOTk5IDE2Ljk2MSAxMC42MDJWNTEuOTkzeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik02NS4zNDQgNDAuMjZMNDYuMTg5IDUxLjk3OXYyMi44NDdsMTYuODk5LTEwLjU3NiAxMi41MzkgNi45NzQgMi42MDktMS41MDV2LTIuNzY1bC0xMi43ODQtNy4xMTJ6Ii8+JiN4YTs8L3N2Zz4=',
        'iam': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE2LjQyMDAwMDA3NjI5Mzk0NSIgaGVpZ2h0PSIyMC4wNDk5OTkyMzcwNjA1NDciIGZpbGwtcnVsZT0iZXZlbm9kZCIgdmlld0JveD0iMCAwIDE2LjQyMDAwMDA3NjI5Mzk0NSAyMC4wNDk5OTkyMzcwNjA1NDciPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik04LjIxIDBMMCAzLjQydjUuNjNjMCA1LjA2IDMuNSA5LjggOC4yMSAxMSA0LjcxLTEuMTUgOC4yMS01Ljg5IDguMjEtMTAuOTVWMy40MnptMCAzLjc5YTIuNjMgMi42MyAwIDAgMSAxLjAwNSA1LjA2QTIuNjMgMi42MyAwIDAgMSA2LjM1IDQuNTZhMi42MyAyLjYzIDAgMCAxIDEuODYtLjc3em00LjExIDExLjE1YTguNjQgOC42NCAwIDAgMS00LjExIDIuOTMgOC42NCA4LjY0IDAgMCAxLTQuMTEtMi45M3YtMi4yNWMwLTEuNjcgMi43NC0yLjUyIDQuMTEtMi41MnM0LjExLjg1IDQuMTEgMi41MnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNOC4yMSAwdjMuNzlhMi42MyAyLjYzIDAgMSAxIDAgNS4yNnYxLjEyYzEuMzcgMCA0LjExLjg1IDQuMTEgMi41MnYyLjI1YTguNjQgOC42NCAwIDAgMS00LjExIDIuOTNWMjBjNC43MS0xLjE1IDguMjEtNS44OSA4LjIxLTEwLjk1VjMuNDJ6Ii8+JiN4YTs8L3N2Zz4=',
        'identity-aware proxy': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE5Ljk5IiBoZWlnaHQ9IjEwLjQxIiB2aWV3Qm94PSIwIDAgMTkuOTkgMTAuNDEiPiYjeGE7CTxwYXRoIGQ9Ik05Ljg0LjIxYTUuMSA1LjEgMCAxIDAgNS4xIDUuMWgwYTUuMSA1LjEgMCAwIDAtNS4xLTUuMXptMCA5LjA4YTQgNCAwIDEgMSA0LTRoMGE0IDQgMCAwIDEtNCA0LjAxeiIgZmlsbD0iIzQyODVmNCIvPiYjeGE7CTxwYXRoIGQ9Ik0xMS43NiA1LjkyYTIuMDkgMi4wOSAwIDAgMC0uMjgtLjIyIDMuMTEgMy4xMSAwIDAgMC0yLjYxLS4yOCAyLjMxIDIuMzEgMCAwIDAtLjg5LjQ3Ljg2Ljg2IDAgMCAwLS4zNy42NXYxaDQuNDd2LS44MmExIDEgMCAwIDAtLjMyLS44ek05Ljg0IDQuNzRhMS4xNiAxLjE2IDAgMSAwLTEuMTctMS4xNWgwYTEuMTcgMS4xNyAwIDAgMCAxLjE3IDEuMTV6IiBmaWxsPSIjNjY5ZGY2Ii8+JiN4YTsJPHBhdGggZD0iTTE2LjI5IDUuNmgyLjIxbC0uNzcuNzhoMS4wNGwxLjIyLTEuMjMtMS4yMi0xLjIyaC0xLjA0bC43Ny43N2gtMi4yMXoiIGZpbGw9IiNhZWNiZmEiLz4mI3hhOwk8cGF0aCBkPSJNMTcuODggMS43M1YwaC0xLjczbC0uNzMuNzRoMS4wOWwtLjk4Ljk3LjY0LjY0Ljk4LS45N3YxLjA5em0tMi40NiA3Ljk1bC43My43M2gxLjczVjguNjhsLS43My0uNzN2MS4wOWwtLjk4LS45Ny0uNjQuNjMuOTguOTh6TTEuMzQgMy44NkExLjM1IDEuMzUgMCAxIDAgMi43IDUuMjFhMS4zNSAxLjM1IDAgMCAwLTEuMzYtMS4zNXptMCAyLjFhLjc2Ljc2IDAgMSAxIC43Ni0uNzVoMGEuNzYuNzYgMCAwIDEtLjc2Ljc1eiIgZmlsbD0iIzY2OWRmNiIvPiYjeGE7PC9zdmc+',
        'integration connectors': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc1IiB2ZXJzaW9uPSIxLjEiIHZpZXdCb3g9IjAgMCAxNTUuMzAyNzM0Mzc1IDE1NS4yODYyMzk2MjQwMjM0NCIgaGVpZ2h0PSIxNTUuMjg2MjM5NjI0MDIzNDQiIHdpZHRoPSIxNTUuMzAyNzM0Mzc1Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgkuc3Qwe2ZpbGw6I2FlY2JmYTt9CS5zdDF7ZmlsbDojNjY5ZGY2O30JLnN0MntmaWxsOiM0Mjg1ZjQ7fQk8L3N0eWxlPgkmI3hhOyAgPHBhdGggY2xhc3M9InN0MCIgZD0ibSA4NS42OTM0OTMsMzguNzY3ODcyIHYgMjMuMTExNjkgaCAxNS40OTk5OTcgdiAtMjMuMTExNjkgeiBtIC0zMS4xNjIyNDMsMCB2IDIzLjExMTY5IGggMTUuNSBWIDM4Ljc2Nzg3MiBaIE0gNzcuODg4NjczLDEuMjUyNzM5NWUtNiBDIDM2LjAxMzkxOSwxLjI1MjczOTVlLTYgMCwzMy45NzYwMDIgMCw3Ny4xNzU3ODIgYyAwLDE2LjQzNTE2IDUuNTY5NzkzLDM1LjIwODE2OCAxOC4yMTQ4NDQsNTAuMzMzOTc4IDcuMTc0MjI2LDguNTgxNyAxNi43MzUxNTksMTUuODUwNzkgMjguNTgxOTU5LDIwLjUzNDMyIGwgLTAuMDE4NjcsLTE2LjMxODcgQyAzOS44ODEyNDUsMTI4LjEyNjE5IDM0LjI4MjYxMSwxMjMuMzQzMjEgMjkuNzIyNjU3LDExNy44ODg2NyAxOS42NjQ3NTcsMTA1Ljg1NzU3IDE1LjAwMDAwMSw5MC4xMjgyMTIgMTUsNzcuMTc1NzgyIDE1LDQyLjMyMDQyMiA0NC4xMTY2MzgsMTUuMDAwMDAxIDc3Ljg4ODY3MywxNS4wMDAwMDEgWiIvPiYjeGE7ICA8cGF0aCBjbGFzcz0ic3QxIiBkPSJtIDc4LjAzMjE2MywxMjQuNDUxOTQgYyAtMjEuNDQ2Mjg1LDAgLTM5LjI4NjcyNiwtMTYuMzc3NjkgLTM5LjI4NjcyNiwtNDAuNjg4NTc4IGwgMC4yMDc3NjIsLTIxLjg4MzggaCAzOS4wNzg5NjQgeiIvPiYjeGE7ICA8cGF0aCBjbGFzcz0ic3QyIiBkPSJtIDc4LjAzMjE2MSw2MS44Nzk1NjcgdiA2Mi41NzIzNzMgYyAtMi43Mzc3MzksMCAtNS40MTYxNCwtMC4yNjg3NSAtOC4wMDY3NDcsLTAuNzg0OTYgdiAzMS42MTkyNiBIIDg1LjYwOTQ3NSBWIDEyMy40MDM0MyBDIDEwNi42NDQyLDExOC44ODQzNCAxMTYuOTIwMjMsMTAwLjY5NzE2IDExNi45MjAyMyw4My45NDMzMDUgViA2MS44Nzk1NjcgWiBNIDc3Ljg4ODY3MiwwIHYgMTUuMDAwMDAyIGMgMzAuOTM1OTU4LDAgNjIuNDE0MDU4LDIzLjk3MTE5OSA2Mi40MTQwNTgsNjQuMDgyMDI5IDAsMTAuMzkyNTcxIC00LjM1NTU1LDI1Ljg4NzQwOSAtMTQuMjc5MywzOC4wNzAzMDkgLTQuNTQ3NTUsNS41ODI4IC0xMC4xNTk2MiwxMC41NzAzNyAtMTcuMTQ0MzcsMTQuMzM1ODkgbCAwLjEzNTQ0LDE2LjMyODcyIGMgMTIuMDExNjQsLTQuOTE0NDUgMjEuNTY3NDQsLTEyLjUwNzYyIDI4LjYzOTc5LC0yMS4xOSBDIDE1MC4wMzMsMTExLjQzMDIyIDE1NS4zMDI3Myw5My4zNzM2NjEgMTU1LjMwMjczLDc5LjA4MjAzMSAxNTUuMzAyNzMsMzEuMDIzOTA0IDExNi43MDgzMywwIDc3Ljg4ODY3MiwwIFoiLz4mI3hhOzwvc3ZnPg==',
        'jobs search': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE5LjkyMTQ0MjAzMTg2MDM1IiBoZWlnaHQ9IjE5Ljc3ODMyMDMxMjUiIHZpZXdCb3g9Ii0wLjAwMDQ0MTU1NzE3NDc4MTMzNzQgMC4yNSAxOS45MjE0NDIwMzE4NjAzNSAxOS43NzgzMjAzMTI1Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qxe2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0MntmaWxsLXJ1bGU6ZXZlbm9kZH0mI3hhOwkuc3Qze2ZpbGw6IzY2OWRmNjt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNNC40NjEgMTYuMjRhMyAzIDAgMSAxIDAtNiAzIDMgMCAxIDEgMCA2em0zLjYzLS40YTQuNDMgNC40MyAwIDAgMC01LjA0OS02LjcxNEE0LjQzIDQuNDMgMCAwIDAgLjAxMSAxMy4zMmE0LjkxIDQuOTEgMCAwIDAgMCAuNjcgMy40MyAzLjQzIDAgMCAwIC4wOS40NGwuMDYuMjFhNC41OSA0LjU5IDAgMCAwIC4zNC43OSA0LjI0IDQuMjQgMCAwIDAgLjc2IDFsLjE1LjE1LjMzLjI3YTQuMTYgNC4xNiAwIDAgMCAuNzMuNDQgNC40NCA0LjQ0IDAgMCAwIDQuNTQtLjI5bDIuOTMgMi45M2EuMzMuMzMgMCAwIDAgLjQ3IDBsLjY2LS42NWEuMzMuMzMgMCAwIDAgMC0uNDd6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTkuODExIDE0LjU4YTUuNDEgNS40MSAwIDAgMCAuMi0xLjUxIDUuNTMgNS41MyAwIDAgMC01LjYxLTUuNDIgNS44MiA1LjgyIDAgMCAwLTEuOTIuMzVWMy44M2EuNjIuNjIgMCAwIDEgLjYyLS42MmgxNi4xOWEuNjMuNjMgMCAwIDEgLjYzLjYyVjE0YS42My42MyAwIDAgMS0uNjMuNjN6Ii8+JiN4YTsJPGcgY2xhc3M9InN0MiI+JiN4YTsJCTxwYXRoIGNsYXNzPSJzdDMiIGQ9Ik0xMy41OTEgMy4yMVYxLjczaC00LjQ0djEuNDhoLTEuNDlWLjg3YS42My42MyAwIDAgMSAuNjMtLjYyaDYuMTZhLjYyLjYyIDAgMCAxIC42Mi42MnYyLjM0eiIvPiYjeGE7CQk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTUuMDcxIDMuMjFoLTEuNDhsMS40OC0uNDd6bS01LjkzIDBoLTEuNDlsMS40OS0uNTR6Ii8+JiN4YTsJPC9nPiYjeGE7PC9zdmc+',
        'key management service': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjMxMC43NzU2MDY1NDM4NjAyNSIgaGVpZ2h0PSIzNzcuOTUzMDI4ODM1NTI1NDYiIHZpZXdCb3g9Ii0wLjE0MDAwMDAwMDU5NjA0NjQ1IC0wLjQ2NzAwMDAwNzYyOTM5NDUzIDgyLjIyNTk5NzkyNDgwNDY5IDEwMC4wMDAwMDc2MjkzOTQ1MyI+JiN4YTs8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qxe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MntmaWxsOiNmZmY7fSYjeGE7PC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNNDAuOTczLS40NjdsNDEuMTEzIDE3LjQ5M3YyOS42NTRjMCAyNy40MTgtMjQuNjA4IDUwLjgzNi00MS4xMTMgNTIuODUzeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik00MC45NzMtLjQ2N0wtLjE0IDE3LjAyNXYyOS42NTRjMCAyNy40MTggMjQuNjA4IDUwLjgzNiA0MS4xMTMgNTIuODUzeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik00MS4yNTMgMTYuNjA1Yy05LjU4NCAwLTE3LjQ0NSA3Ljg2Mi0xNy40NDUgMTcuNDQ1IDAgOC4wODQgNS41OTQgMTQuOTQyIDEzLjA5NiAxNi44OTF2OS40ODhoLTkuODY5djguNzAxaDkuODY5djUuMzc3aC02LjMxNXY4LjcwMWg2LjMxNXYyLjE5N2g4LjcwMVY1MC45NDFDNTMuMTA2IDQ4Ljk5MiA1OC43IDQyLjEzNCA1OC43IDM0LjA1YzAtOS41ODQtNy44NjMtMTcuNDQ1LTE3LjQ0Ny0xNy40NDV6bTAgOC42OTlBOC42OCA4LjY4IDAgMCAxIDUwIDM0LjA1YTguNjggOC42OCAwIDAgMS04Ljc0OCA4Ljc0NiA4LjY4IDguNjggMCAwIDEtOC43NDYtOC43NDYgOC42OCA4LjY4IDAgMCAxIDguNzQ2LTguNzQ2eiIvPiYjeGE7PC9zdmc+',
        'kubernetes engine': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjMyOS45MjU5OTcyMzE3OTM4IiBoZWlnaHQ9IjM3OC4yODQ5OTAzMTEyNzg4IiB2aWV3Qm94PSIwIDAgODcuMjkyOTk5MjY3NTc4MTIgMTAwLjA4Nzk5NzQzNjUyMzQ0Ij4mI3hhOzxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiNhZWNiZmE7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6IzQyODVmNDt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik00My43NTEgMEwwIDI1LjQ2NXYyLjU4OCA0Ni45Mmw0My43NTIgMjUuMTE1IDQzLjU0MS0yNS4xMjFWMjUuNDczem0yLjQzOCAxMS44NTNsMzIuMTAzIDE4Ljc4MlY2OS43N0w0My43MzkgODkuNzA1IDkgNjkuNzYyVjMwLjY0MWwzMi4xOS0xOC43MzZ2MTQuMTU0TDI0LjUwMyAzNi4xNTNsMTkuMTcyIDExLjUwMiAxOC44ODYtMTEuNTU0LTE2LjM3Mi0xMC4wMjR6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTIyLjAyNSA0MC40OTZsLjE2NiAxOS4xNDMtMTMuMjQ3IDcuMzN2Mi43NDJsMi42MzcgMS41MTQgMTIuNjQ4LTYuOTk5IDE2Ljk2MSAxMC42MDJWNTEuOTkzeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik02NS4zNDQgNDAuMjZMNDYuMTg5IDUxLjk3OXYyMi44NDdsMTYuODk5LTEwLjU3NiAxMi41MzkgNi45NzQgMi42MDktMS41MDV2LTIuNzY1bC0xMi43ODQtNy4xMTJ6Ii8+JiN4YTs8L3N2Zz4=',
        'life sciences': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE4LjYwMDAwMDM4MTQ2OTcyNyIgdmlld0JveD0iMCAwIDIwIDE4LjYwMDAwMDM4MTQ2OTcyNyI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6I2FlY2JmYTt9JiN4YTsJLnN0MXtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDJ7ZmlsbC1ydWxlOmV2ZW5vZGR9JiN4YTsJLnN0M3tmaWxsOiM2NjlkZjY7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPGNpcmNsZSBjeD0iMTAiIGN5PSI5LjMiIHI9IjEuNiIgY2xhc3M9InN0MCIvPiYjeGE7CTxwYXRoIGQ9Ik0xMi42OSA1LjhsLS43NC0uN0g1LjU4djEuNGg2LjM3eiIgY2xhc3M9InN0MSBzdDIiLz4mI3hhOwk8Y2lyY2xlIGN4PSI0LjgiIGN5PSI1LjgiIHI9IjEuMjMiIGNsYXNzPSJzdDMiLz4mI3hhOwk8Y2lyY2xlIGN4PSIxNS4yIiBjeT0iNS44IiByPSIxLjYiIGNsYXNzPSJzdDAiLz4mI3hhOwk8cGF0aCBkPSJNMTQuMzggMTMuNXYtMS40SDguMWwtLjc0LjcuNzQuN3oiIGNsYXNzPSJzdDEgc3QyIi8+JiN4YTsJPGNpcmNsZSBjeD0iNC44IiBjeT0iMTIuOCIgcj0iMS42IiBjbGFzcz0ic3QwIi8+JiN4YTsJPGNpcmNsZSBjeD0iMTUuMiIgY3k9IjEyLjgiIHI9IjEuMjMiIGNsYXNzPSJzdDMiLz4mI3hhOwk8cGF0aCBkPSJNMTUuNiAxLjZsLS43NC0uN0gyLjE4djEuNGgxMi42OHoiIGNsYXNzPSJzdDEgc3QyIi8+JiN4YTsJPGNpcmNsZSBjeD0iMS42IiBjeT0iMS42IiByPSIxLjIzIiBjbGFzcz0ic3QzIi8+JiN4YTsJPGNpcmNsZSBjeD0iMTguNCIgY3k9IjEuNiIgcj0iMS42IiBjbGFzcz0ic3QwIi8+JiN4YTsJPHBhdGggZD0iTTE3Ljg0IDE3Ljd2LTEuNEg1LjE0bC0uNzQuNy43NC43eiIgY2xhc3M9InN0MSBzdDIiLz4mI3hhOwk8Y2lyY2xlIGN4PSIxLjYiIGN5PSIxNyIgcj0iMS42IiBjbGFzcz0ic3QwIi8+JiN4YTsJPGNpcmNsZSBjeD0iMTguNCIgY3k9IjE3IiByPSIxLjIzIiBjbGFzcz0ic3QzIi8+JiN4YTs8L3N2Zz4=',
        'looker': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc4OTgwMSIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSItOS41MzY3NDMxNjQwNjI1ZS03IDAgMjA4LjA1NjU0OTA3MjI2NTYyIDMzNC42MTMxNTkxNzk2ODc1IiBoZWlnaHQ9IjMzNC42MTMxNTkxNzk2ODc1IiB3aWR0aD0iMjA4LjA1NjU0OTA3MjI2NTYyIj4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgkuc3Qwe2ZpbGw6IzU5ODZmMjt9CS5zdDF7ZmlsbDojNmY5OGY0O30JLnN0MntmaWxsOiNkNmUzZmI7fQk8L3N0eWxlPgkmI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTQuMjQ2MjUyNCwxNS42NzE5MTEpIiBpZD0ibGF5ZXIxIj4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiB0cmFuc2Zvcm09InNjYWxlKDAuMjY0NTgzMzMpIiBkPSJtIDQwOS4yMjI2Niw0MTkuMDk5NjEgYyAtMzYuNjA4MTEsMCAtNzIuMDc2NjcsNS4wNzUzIC0xMDUuNzUzOTEsMTQuNTMxMjUgbCA0OS4wMzUxNiwxMjAuMDQxMDIgYyAxOC4yNjE3MiwtMy45Mzg5OSAzNy4yMjE5NiwtNi4wNjgzNiA1Ni43MTg3NSwtNi4wNjgzNiAxNDYuOTM1MTQsMCAyNjQuNjc3NzMsMTE3LjczNDc3IDI2NC42Nzc3MywyNjQuNjY5OTIgMCwxNDYuOTM1MTQgLTExNy43NDI1OSwyNjQuNjY5OTYgLTI2NC42Nzc3MywyNjQuNjY5OTYgLTE0Ni45MzUxNiwwIC0yNjQuNjY5OTEsLTExNy43MzQ4MiAtMjY0LjY2OTkzLC0yNjQuNjY5OTYgMCwtOTkuMTg3NjMgNTMuNjg5ODMsLTE4NS4wMDU5NiAxMzMuNzU1ODYsLTIzMC4zNDc2NiBMIDIyOS42MjY5NSw0NjIuNzUgQyAxMDMuMDI0Nyw1MjguMjI0NzQgMTYuMDQ4ODI3LDY2MC41MDUyMyAxNi4wNDg4MjgsODEyLjI3MzQ0IGMgMi4zZS01LDIxNi4zODM3NiAxNzYuNzkwMDYyLDM5My4xNzM4NiAzOTMuMTczODMyLDM5My4xNzM4NiAyMTYuMzgzNzMsMCAzOTMuMTgxNjQsLTE3Ni43OTAxIDM5My4xODE2NCwtMzkzLjE3Mzg2IDNlLTUsLTIxNi4zODM3OCAtMTc2Ljc5Nzg3LC0zOTMuMTczODMgLTM5My4xODE2NCwtMzkzLjE3MzgzIHoiLz4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QxIiBkPSJtIDE4OS45NDMzNiw4Ni4yNSBjIC05NS4xMzAzMzEsMCAtMTczLjE3OTY4OCw3OC4wNTUyMiAtMTczLjE3OTY4OCwxNzMuMTg1NTUgLTZlLTYsOTUuMTMwMzMgNzguMDQ5MzUzLDE3My4xNzk2OCAxNzMuMTc5Njg4LDE3My4xNzk2OCA5LjAxNjE4LDAgMTcuODc1OCwtMC43MDgzMiAyNi41MzMyLC0yLjA1ODU5IGwgLTM0LjgyODEyLC04NS4yNjU2MiBjIC00NC4xNTczLC00LjA4NjY5IC03Ny45NTUwOCwtNDAuNTA3MDUgLTc3Ljk1NTA4LC04NS44NTU0NyAwLC00OC4xNTAzOSAzOC4wOTk2MiwtODYuMjU1ODYgODYuMjUsLTg2LjI1NTg2IDEzLjE1OTc3LDAgMjUuNTU4ODgsMi44NjI0NiAzNi42NDQ1Myw3Ljk4MjQyIGwgNjQuNTU0NjksLTYxLjkxOTkyIEMgMjYyLjYwODM3LDk4LjUzMzkxIDIyNy42MjkyOSw4Ni4yNSAxODkuOTQzMzYsODYuMjUgWiBtIDEzOC44ODg2Nyw3MC4xNjIxMSAtNjMuNDI3NzMsNjAuODM1OTQgYyA2Ljg3NjM4LDEyLjQyNjc4IDEwLjc4OTA2LDI2Ljc4ODE1IDEwLjc4OTA2LDQyLjE4NzUgMCwyMS43NjcxMiAtNy44MDQxNSw0MS40NjU0IC0yMC43ODUxNiw1Ni41MzMyIGwgMzQuNTIzNDQsODQuNTE5NTMgYyA0NC4xNzM4NywtMzEuNDg3NTEgNzMuMTkxNDEsLTgzLjA3ODkyIDczLjE5MTQxLC0xNDEuMDUyNzMgMCwtMzguNDgzNTUgLTEyLjc4MiwtNzQuMTY1MzIgLTM0LjI5MTAyLC0xMDMuMDIzNDQgeiIgdHJhbnNmb3JtPSJzY2FsZSgwLjI2NDU4MzMzKSIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDIiIHRyYW5zZm9ybT0ic2NhbGUoMC4yNjQ1ODMzMykiIGQ9Im0gNDA2LjEzNjcyLC01OS4yMzI0MjIgYyAtNTguODE1NDcsOGUtNiAtMTA3LjEwMzUyLDQ4LjI4ODA0NSAtMTA3LjEwMzUyLDEwNy4xMDM1MTYgMCwxOC40OTQ0NTEgNC43ODEwMSwzNS45NDUwMTcgMTMuMTU2MjUsNTEuMTgzNTk0IGwgNDQuMzEyNSwtNDIuNTAzOTA3IGMgLTAuNDc1NjcsLTIuODIwNzc1IC0wLjc3NTM5LC01LjcwNzU2NCAtMC43NzUzOSwtOC42Nzk2ODcgMCwtMjguMTc2MzggMjIuMjMzNzgsLTUwLjQxMDE1MjUgNTAuNDEwMTYsLTUwLjQxMDE1NjUgMjguMTc2MzgsLTRlLTYgNTAuNDEwMTUsMjIuMjMzNzcwNSA1MC40MTAxNiw1MC40MTAxNTY1IDAsMjguMTc2MzgxIC0yMi4yMzM3OCw1MC40MTIxMTMgLTUwLjQxMDE2LDUwLjQxMjEwOSAtNS4wNjg2OSwtMTBlLTcgLTkuOTM0MTcsLTAuNzQ1NjMxIC0xNC41MjM0NCwtMi4wODk4NDQgbCAtNDMuMzYxMzMsNDEuNTkxODAxIGMgMTYuNzMyMjMsMTAuODQ3OTUgMzYuNjExMjMsMTcuMTg5NDUgNTcuODg0NzcsMTcuMTg5NDUgNTguODE1NDksMTBlLTYgMTA3LjEwMzUxLC00OC4yODgwNCAxMDcuMTAzNTEsLTEwNy4xMDM1MTYgMCwtNTguODE1NDgzIC00OC4yODgwMiwtMTA3LjEwMzUyMyAtMTA3LjEwMzUxLC0xMDcuMTAzNTE2IHoiLz4mI3hhOyAgPC9nPiYjeGE7PC9zdmc+',
        'managed ms ad': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmcxMDk4NTgiIHZlcnNpb249IjEuMSIgdmlld0JveD0iMCAwIDE0Ni4zNjkxNDA2MjUgMTY1Ljk2NDg0Mzc1IiBoZWlnaHQ9IjE2NS45NjQ4NDM3NSIgd2lkdGg9IjE0Ni4zNjkxNDA2MjUiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojNjY5ZGY2O30JLnN0MXtmaWxsOiM0Mjg1ZjQ7fQkuc3Qye2ZpbGw6I2FlY2JmYTt9CTwvc3R5bGU+CSYjeGE7ICA8ZyB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMzIuODI0MjE5LC02Ny41NTg1OTQpIiBpZD0ibGF5ZXIxIj4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJtIDk3Ljc1MTU3Niw3Ny45MDE2MzkgNzIuMjgzNzM0LDg4LjU3NTY2MSAtNzIuMjgzNzM1LDU4LjYxMzQ5IDEwZS03LC0xNDcuMTg5MTUxIi8+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MSIgZD0iTSA5Ny42NzE4NzUsMjMzLjUyMzQ0IDE3OS4xOTMzNiwxNjcuNDE5OTIgOTcuNzAxMTcyLDY3LjU1ODU5NCA5Ny44MDI3MzMsODguMjQ2MDk0IDE2MC44NzY5NSwxNjUuNTM1MTYgOTcuODMyMDMxLDIxNi42NTgyIFoiLz4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJtIDk3LjcwMTE3Miw2Ny41NTg1OTQgLTM0LjIzODI4MSw0Mi43OTg4MjYgMTAuMTUwMzksOC4xMjExIDI0LjE4OTQ1MywtMzAuMjMyNDI2IHogbSAwLjEzMDg1OSwxNDkuMDk5NjA2IC0yMi4xMDc0MjIsLTE4LjYzNDc2IC04LjM3ODkwNiw5LjkzOTQ1IDMwLjMyNjE3MiwyNS41NjA1NSB6Ii8+JiN4YTsgICAgPHBhdGggY2xhc3M9InN0MiIgZD0ibSA1Ny4xMTUyMzQsMTY4LjAyNzM0IGMgLTEzLjMyMTI5MiwwIC0yNC4yOTEwMTYsMTAuOTcxNjggLTI0LjI5MTAxNSwyNC4yOTI5NyAtMTBlLTcsMTMuMzIxMjkgMTAuOTY5NzIzLDI0LjI5MTAyIDI0LjI5MTAxNSwyNC4yOTEwMiAxMy4zMjEyOTIsMCAyNC4yOTI5NywtMTAuOTY5NzMgMjQuMjkyOTY5LC0yNC4yOTEwMiAxMGUtNywtMTMuMzIxMjkgLTEwLjk3MTY3NywtMjQuMjkyOTcgLTI0LjI5Mjk2OSwtMjQuMjkyOTcgeiBtIDAsMTYgYyA0LjY3NDI1OSwwIDguMjkyOTY5LDMuNjE4NzEgOC4yOTI5NjksOC4yOTI5NyAwLDQuNjc0MjYgLTMuNjE4NzEsOC4yOTEwMiAtOC4yOTI5NjksOC4yOTEwMiAtNC42NzQyNTgsMCAtOC4yOTEwMTYsLTMuNjE2NzYgLTguMjkxMDE1LC04LjI5MTAyIC0xMGUtNywtNC42NzQyNiAzLjYxNjc1NywtOC4yOTI5NyA4LjI5MTAxNSwtOC4yOTI5NyB6IG0gMCwtODEuOTE2MDEgYyAtMTMuMzIxMjkyLDAgLTI0LjI5MTAxNiwxMC45Njk3MiAtMjQuMjkxMDE1LDI0LjI5MTAxIC0xMGUtNywxMy4zMjEzIDEwLjk2OTcyMywyNC4yOTI5NyAyNC4yOTEwMTUsMjQuMjkyOTcgMTMuMzIxMjkyLDAgMjQuMjkyOTcsLTEwLjk3MTY3IDI0LjI5Mjk2OSwtMjQuMjkyOTcgMTBlLTcsLTEzLjMyMTI5IC0xMC45NzE2NzcsLTI0LjI5MTAxIC0yNC4yOTI5NjksLTI0LjI5MTAxIHogbSAwLDE2IGMgNC42NzQyNTksMCA4LjI5Mjk2OSwzLjYxNjc2IDguMjkyOTY5LDguMjkxMDEgMCw0LjY3NDI2IC0zLjYxODcxLDguMjkyOTcgLTguMjkyOTY5LDguMjkyOTcgLTQuNjc0MjU4LDAgLTguMjkxMDE2LC0zLjYxODcxIC04LjI5MTAxNSwtOC4yOTI5NyAtMTBlLTcsLTQuNjc0MjUgMy42MTY3NTcsLTguMjkxMDEgOC4yOTEwMTUsLTguMjkxMDEgeiIvPiYjeGE7ICA8L2c+JiN4YTs8L3N2Zz4=',
        'memorystore': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMCAxLjk0aDMuMzN2Mi41OEgwem0wIDQuNTFoMy4zM3YyLjU4SDB6bTAgNC41MmgzLjMzdjIuNThIMHptMCA0LjUxaDMuMzN2Mi41OEgwek0xNi42NyAxLjk0SDIwdjIuNThoLTMuMzN6bTAgNC41MUgyMHYyLjU4aC0zLjMzem0wIDQuNTJIMjB2Mi41OGgtMy4zM3ptMCA0LjUxSDIwdjIuNThoLTMuMzN6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTE2LjY3IDEuOTRsMi42NiAyLjU4aC0yLjY2em0wIDQuNTFsMi42NiAyLjU4aC0yLjY2em0wIDQuNTJsMi42NiAyLjU4aC0yLjY2em0wIDQuNTFsMi42NiAyLjU5aC0yLjY2eiIgZmlsbC1ydWxlPSJldmVub2RkIi8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTMuMzMgMjBoMTMuMzRWMEgzLjMzem02LTlINmw0LjY3LTcuNzRWOUgxNGwtNC42NyA3Ljc0eiIgZmlsbC1ydWxlPSJldmVub2RkIi8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE0IDkuMDNoLTMuMzNWMGg2djIwSDkuMzN2LTMuMjN6IiBmaWxsLXJ1bGU9ImV2ZW5vZGQiLz4mI3hhOzwvc3ZnPg==',
        'natural language api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE2IiB2aWV3Qm94PSIwIDAgMjAgMTYiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDF7ZmlsbDojNDI4NWY0O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTUgMmgzdjEyaC0zdjJoMyAydi0yVjIgMGgtMi0zeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xOCAydjFsMi0xem0yIDEydi0xbC0yIDF6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTUgMTRIMlYyaDNWMEgyIDB2MiAxMiAyaDIgM3oiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMCAxNHYtMWwyIDF6TTIgMnYxTDAgMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNNSA3aDEwdjJINXptMCAzaDEwdjJINXptMC02aDEwdjJINXoiLz4mI3hhOzwvc3ZnPg==',
        'network intelligence': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc4MTMzMSIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSIwLjAwMDAwNzYyOTM5NDUzMTI1IDAuMDAwMDAzODE0Njk3MjY1NjI1IDQzNi43MTcwMTA0OTgwNDY5IDM5OS43NTMzNTY5MzM1OTM3NSIgaGVpZ2h0PSIzOTkuNzUzMzU2OTMzNTkzNzUiIHdpZHRoPSI0MzYuNzE3MDEwNDk4MDQ2OSI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4JLnN0MHtmaWxsOiM1OTg2ZjI7fQk8L3N0eWxlPgkmI3hhOyAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoMTExLjg3MDE3LDUxLjExNjc3NykiIGlkPSJsYXllcjEiPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDAiIHRyYW5zZm9ybT0ic2NhbGUoMC4yNjQ1ODMzMykiIGQ9Ik0gMzkyLjQ2MDk0LC0xOTMuMTk3MjcgQSAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIDI0MS4yNDIxOSwtNDEuOTc4NTE2IDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgMzkyLjQ2MDk0LDEwOS4yNDAyMyAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIDU0My42Nzk2OSwtNDEuOTc4NTE2IDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgMzkyLjQ2MDk0LC0xOTMuMTk3MjcgWiBNIDkwNy4yMTg3NSwtMzEuNjk5MjE5IEEgMTUxLjIxODM0LDE1MS4yMTgzNCAwIDAgMCA3NjQuNTUyNzMsNjkuNzA3MDMxIEggNjQ5LjM1NTQ3IEEgNTEuMDI4NzI0LDUxLjAyODcyNCAwIDAgMCA2MDUuMjc3MzQsOTUuMDI3MzQ0IEwgNTEyLjk4MjQyLDI1My4yNTU4NiBIIDI3Mi40NTExNyBMIDE4MC4xNTQzLDk1LjAyNzM0NCBBIDUxLjAyODcyNCw1MS4wMjg3MjQgMCAwIDAgMTM2LjA3ODEyLDY5LjcwNzAzMSBIIDIxLjkyMTg3NSBBIDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgLTEyMC40ODgyOCwtMzAuNjgzNTk0IDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgLTI3MS43MDcwMywxMjAuNTMzMiAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIC0xMjAuNDg4MjgsMjcxLjc1MTk1IDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgMjEuNjg1NTQ3LDE3MS43NTM5MSBIIDEwNi43NzE0OCBMIDE4Mi4xNDI1OCwzMDAuOTY2OCA2Mi4wMzEyNSw1MDYuNTQ0OTIgSCAtMTI4LjgxODM2IEEgMTUxLjIxODM0LDE1MS4yMTgzNCAwIDAgMCAtMjcxLjU5NzY2LDQwNC44MTQ0NSAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIC00MjIuODE2NDEsNTU2LjAzMzIgMTUxLjIxODM0LDE1MS4yMTgzNCAwIDAgMCAtMjcxLjU5NzY2LDcwNy4yNTE5NSAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIC0xMjkuODkyNTgsNjA4LjU5MTggSCA2NC43MDcwMzEgTCAxODMuNzA1MDgsODE3Ljc1MzkxIDEwNi43NzE0OCw5NDkuNjQyNTggSCAyMy42OTMzNTkgQSAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIC0xMTkuNzg1MTYsODQ1LjkxNDA2IDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgLTI3MS4wMDM5MSw5OTcuMTMyODEgMTUxLjIxODM0LDE1MS4yMTgzNCAwIDAgMCAtMTE5Ljc4NTE2LDExNDguMzUxNiAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIDIxLjIyMDcwMywxMDUxLjY5MTQgSCAxMzYuMDc4MTIgYSA1MS4wMjg3MjQsNTEuMDI4NzI0IDAgMCAwIDQ0LjA3NjE4LC0yNS4zMTI1IEwgMjc0Ljg2OTE0LDg2NC4wMDM5MSBIIDUxMC41NjI1IGwgOTQuNzE0ODQsMTYyLjM3NDk5IGEgNTEuMDI4NzI0LDUxLjAyODcyNCAwIDAgMCA0NC4wNzgxMywyNS4zMTI1IGggMTE2LjI1MzkxIGEgMTUxLjIxODM0LDE1MS4yMTgzNCAwIDAgMCAxNDEuMzQ1Nyw5Ny42Mjg5IEEgMTUxLjIxODM0LDE1MS4yMTgzNCAwIDAgMCAxMDU4LjE3MTksOTk4LjEwMTU2IDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgOTA2Ljk1NTA4LDg0Ni44ODQ3NyAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIDc2My44MTQ0NSw5NDkuNjQyNTggSCA2NzguNjYyMTEgTCA2MDAuNzI0NjEsODE2LjAzNTE2IDcyNC4zMzM5OCw2MDguNTkxOCBIIDkzNC4xMzI4MSBBIDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgMTA3Ni41NDg4LDcwOS4yNzkzIDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgMTIyNy43Njc2LDU1OC4wNjI1IDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgMTA3Ni41NDg4LDQwNi44NDM3NSAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIDkzNC40Nzg1Miw1MDYuNTQ0OTIgSCA3MjcuMTM0NzcgTCA2MDIuMzM3ODksMzAyLjU5OTYxIDY3OC42NjIxMSwxNzEuNzUzOTEgaCA4Ni43MzgyOCBBIDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgOTA3LjIxODc1LDI3MC43MzgyOCAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIDEwNTguNDM3NSwxMTkuNTE5NTMgMTUxLjIxODM0LDE1MS4yMTgzNCAwIDAgMCA5MDcuMjE4NzUsLTMxLjY5OTIxOSBaIE0gMzkzLjM2NTIzLDEwMTUuMjQ0MSBhIDE1MS4yMTgzNCwxNTEuMjE4MzQgMCAwIDAgLTE1MS4yMTg3NSwxNTEuMjE4OCAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIDE1MS4yMTg3NSwxNTEuMjE4NyAxNTEuMjE4MzQsMTUxLjIxODM0IDAgMCAwIDE1MS4yMTg3NSwtMTUxLjIxODcgMTUxLjIxODM0LDE1MS4yMTgzNCAwIDAgMCAtMTUxLjIxODc1LC0xNTEuMjE4OCB6Ii8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'partner interconnect': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjEzLjUxOTk5OTUwNDA4OTM1NSIgdmlld0JveD0iMCAtMi4wNjA1NzM0NTA4OTU1MTA2ZS0xNSAyMCAxMy41MTk5OTk1MDQwODkzNTUiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNOS4xOSAxLjYyaDEuNjJ2MTAuMjdIOS4xOXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMCA1Ljk1aDIuN3YxLjYySDB6Ii8+JiN4YTsJPHJlY3QgY2xhc3M9InN0MCIgeD0iMi40MyIgeT0iMy41MiIgd2lkdGg9IjQuODYiIGhlaWdodD0iNi40OSIgcng9Ii4yNCIvPiYjeGE7CTxnIGNsYXNzPSJzdDEiPiYjeGE7CQk8cGF0aCBkPSJNOS4xOSAxLjYyaDEuNjJ2MTAuMjdIOS4xOXptOC4xMSA0LjMzSDIwdjEuNjJoLTIuN3oiLz4mI3hhOwkJPHBhdGggZD0iTTQuNTkgMTEuOXYxLjMzYS4yOS4yOSAwIDAgMCAuMjkuMjloMTAuMjRhLjI5LjI5IDAgMCAwIC4yOS0uMjloMFYxMS45ek0xNS4xMiAwSDQuODhhLjI5LjI5IDAgMCAwLS4yOS4yOWgwdjEuMzNoMTAuODJWLjI5YS4yOS4yOSAwIDAgMC0uMjktLjI5eiIvPiYjeGE7CTwvZz4mI3hhOwk8cmVjdCBjbGFzcz0ic3QwIiB4PSIxMi43IiB5PSIzLjUyIiB3aWR0aD0iNC44NiIgaGVpZ2h0PSI2LjQ5IiByeD0iLjI0Ii8+JiN4YTs8L3N2Zz4=',
        'persistent disk': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE1Ljg0MDAwMDE1MjU4Nzg5IiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMTUuODQwMDAwMTUyNTg3ODkgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMCAxNi4yNVYyMGgxNS44NHYtOC4zM2gtMy43NXY0LjU4eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0xNS44NCAzLjc1VjBIMHY4LjMzaDMuNzVWMy43NXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNMCAxMC40MnYzLjc1aDEwVjkuNThoNS44NFY1LjgzaC0xMHY0LjU5eiIvPiYjeGE7PC9zdmc+',
        'premium network tier': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwLjAyODAxODk1MTQxNjAxNiIgaGVpZ2h0PSIxMC4wMTk3MzA1Njc5MzIxMjkiIHZpZXdCb3g9Ii0wLjAwMDAxOTc3MjAwNTU0MzkyNzY2MiAwIDIwLjAyODAxODk1MTQxNjAxNiAxMC4wMTk3MzA1Njc5MzIxMjkiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTYuMjU4IDIuMjRBOS42MSA5LjYxIDAgMCAwIDEwLjEwOCAwQzUuMjY4IDAgMS4xMzggMy42NS4wMjggOC45YS44MS44MSAwIDEgMCAxLjU4LjM1aDBjLjk1LTQuNTEgNC40Mi03LjY1IDguNS03LjY1YTcuODYgNy44NiAwIDAgMSA0LjQ1IDEuNHptLjQ0IDEuMjlsLTUuODggMi42M2gwYTIgMiAwIDEgMCAxLjEzIDIuNTggMS44MyAxLjgzIDAgMCAwIC4xMi0uNDYuMS4xIDAgMCAwIC4wNSAwbDUtNGMuNTktLjU0LjI3LTEuMDYtLjQyLS43NXoiLz4mI3hhOwk8Y2lyY2xlIGNsYXNzPSJzdDEiIGN4PSIxOC4wNjgiIGN5PSI1Ljk5IiByPSIuODQiLz4mI3hhOwk8Y2lyY2xlIGNsYXNzPSJzdDIiIGN4PSIxOS4xODgiIGN5PSI5LjA0IiByPSIuODQiLz4mI3hhOzwvc3ZnPg==',
        'pub/sub': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE4LjMxOTk5OTY5NDgyNDIyIiBoZWlnaHQ9IjIwLjAwMDAwMTkwNzM0ODYzMyIgdmlld0JveD0iMCAwIDE4LjMxOTk5OTY5NDgyNDIyIDIwLjAwMDAwMTkwNzM0ODYzMyI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MXtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDJ7ZmlsbDojYWVjYmZhO30mI3hhOwk8L3N0eWxlPiYjeGE7CTxkZWZzPiYjeGE7CQk8ZmlsdGVyIGlkPSJBIiB4PSI0LjY0IiB5PSI0LjE5IiB3aWR0aD0iMTQuNzMiIGhlaWdodD0iMTIuNzYiIGZpbHRlclVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgY29sb3ItaW50ZXJwb2xhdGlvbi1maWx0ZXJzPSJzUkdCIj4mI3hhOwkJCTxmZUZsb29kIGZsb29kLWNvbG9yPSIjZmZmIi8+JiN4YTsJCQk8ZmVCbGVuZCBpbj0iU291cmNlR3JhcGhpYyIvPiYjeGE7CQk8L2ZpbHRlcj4mI3hhOwkJPG1hc2sgaWQ9IkIiIHg9IjQuNjQiIHk9IjQuMTkiIHdpZHRoPSIxNC43MyIgaGVpZ2h0PSIxMi43NiIgbWFza1VuaXRzPSJ1c2VyU3BhY2VPblVzZSI+JiN4YTsJCQk8Y2lyY2xlIGN4PSIxMiIgY3k9IjEyLjIzIiByPSIzLjU4IiBmaWx0ZXI9InVybCgjQSkiLz4mI3hhOwkJPC9tYXNrPiYjeGE7CTwvZGVmcz4mI3hhOwk8ZyBjbGFzcz0ic3QwIj4mI3hhOwkJPGNpcmNsZSBjeD0iMTYuMTMiIGN5PSI2LjIxIiByPSIxLjcyIi8+JiN4YTsJCTxjaXJjbGUgY3g9IjIuMTkiIGN5PSI2LjIxIiByPSIxLjcyIi8+JiN4YTsJCTxjaXJjbGUgY3g9IjkuMTYiIGN5PSIxOC4yOCIgcj0iMS43MiIvPiYjeGE7CTwvZz4mI3hhOwk8ZyBtYXNrPSJ1cmwoI0IpIiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMi44NCAtMikiPiYjeGE7CQk8cGF0aCB0cmFuc2Zvcm09Im1hdHJpeCguNSAtLjg3IC44NyAuNSAtNC41OSAyMC41MykiIGQ9Ik0xNC42OSAxMC4yMmgxLjU5djguMDRoLTEuNTl6IiBjbGFzcz0ic3QxIi8+JiN4YTsJCTxwYXRoIHRyYW5zZm9ybT0icm90YXRlKDMzMCA4LjUyMyAxNC4yNDQpIiBkPSJNNC40OSAxMy40NWg4LjA0djEuNTlINC40OXoiIGNsYXNzPSJzdDEiLz4mI3hhOwkJPHBhdGggZD0iTTExLjIgNC4xOWgxLjU5djguMDRIMTEuMnoiIGNsYXNzPSJzdDEiLz4mI3hhOwk8L2c+JiN4YTsJPGcgY2xhc3M9InN0MiI+JiN4YTsJCTxjaXJjbGUgY3g9IjkuMTYiIGN5PSIxMC4yMyIgcj0iMi43OCIvPiYjeGE7CQk8Y2lyY2xlIGN4PSIyLjE5IiBjeT0iMTQuMjUiIHI9IjIuMTkiLz4mI3hhOwkJPGNpcmNsZSBjeD0iMTYuMTMiIGN5PSIxNC4yNSIgcj0iMi4xOSIvPiYjeGE7CQk8Y2lyY2xlIGN4PSI5LjE2IiBjeT0iMi4xOSIgcj0iMi4xOSIvPiYjeGE7CTwvZz4mI3hhOzwvc3ZnPg==',
        'recommendations ai': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM3Ny42ODQ2NTY1OTk1Nzg4MyIgaGVpZ2h0PSIzMzguNTIwNDc5NDMzNDQ2MiIgdmlld0JveD0iMC4wNjUwMDAwMDUwNjYzOTQ4IDAuNDc5OTk5NTQyMjM2MzI4MSA5OS45MjkwMDA4NTQ0OTIxOSA4OS41NjcwMDEzNDI3NzM0NCI+JiN4YTs8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojYWVjYmZhO30mI3hhOwkuc3Qxe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MntmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDN7ZmlsbDojZmZmO30mI3hhOzwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTU5LjU1NCAzNS42MmgzMC45NFY5Ljk4bDkuNS05LjVoLTQ5Ljk0djQ0LjY0em0yOS45ODEgNTQuNDI3VjUzLjYzNWwtOS41IDkuNXYxNy40MTJ6bS01MC4xMjggMFY1My42MzVsLTkuNSA5LjV2MTcuNDEyem0wLTQ0LjU3OVY5LjA1NmwtOS41IDkuNXYxNy40MTJ6IiBmaWxsPSIjYWVjYmZhIi8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTk5Ljk5NCA0NS4xMlYuNDhsLTkuNSA5LjV2MjUuNjR6bS00OS44IDQ0LjkyN2gzOS4zNDJsLTkuNS05LjVINTkuNjkzem0tNTAuMTI4IDBoMzkuMzQybC05LjUtOS41SDkuNTY1em0wLTQ0LjU3OWgzOS4zNDJsLTkuNS05LjVIOS41NjV6IiBmaWxsPSIjNjY5ZGY2Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTUwLjA1NCA0NS4xMmg0OS45NGwtOS41LTkuNWgtMzAuOTR6bTkuNjM5IDM1LjQyN1Y2My4xMzVoMjAuMzQybDkuNS05LjVINTAuMTkzdjM2LjQxMnptLTUwLjEyOCAwVjYzLjEzNWgyMC4zNDJsOS41LTkuNUguMDY1djM2LjQxMnptMC00NC41NzlWMTguNTU2aDIwLjM0Mmw5LjUtOS41SC4wNjV2MzYuNDEyeiIgZmlsbD0iIzQyODVmNCIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDMiIGQ9Ik04Mi42ODUgMTQuMTk4bC0xMC4yNjcgOS4yMDgtNC43ODUtNC4zNS00LjExMiAzLjY3IDguOTMgNy44ODYgMTQuMTgyLTEyLjcyNnoiIGZpbGw9IiNmZmYiLz4mI3hhOzwvc3ZnPg==',
        'retail api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmcyNDYzMyIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSItMC4wMDAwMDE5MDczNDg2MzI4MTI1IDcuMzM4ODIxODg3OTY5OTcxZS03IDI2My4zMDg4MDczNzMwNDY5IDI1OC4xNDg4MDM3MTA5Mzc1IiBoZWlnaHQ9IjI1OC4xNDg4MDM3MTA5Mzc1IiB3aWR0aD0iMjYzLjMwODgwNzM3MzA0NjkiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojNTk4NmYyO30JLnN0MXtmaWxsOiNiNWNiZjk7fQkuc3Qye2ZpbGw6Izc2OWVmNTt9CTwvc3R5bGU+CSYjeGE7ICA8ZyB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMTguNTI5ODk4LDAuMDQyMDczMjUpIiBpZD0ibGF5ZXIxIj4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QwIiB0cmFuc2Zvcm09Im1hdHJpeCgwLjI2NDU4MzMzLDAsMCwwLjI2NDU4MzMzLDAuMTk0MzAzNDIsNS40MzExOTI5KSIgZD0ibSAyNDcuMDUyNzMsLTIwLjY4MTY0MSAtMTQwLjU1ODU5LDIuMjI4NTE2IGMgLTIwLjg2OTIwMiwwLjMzMTk2IC0zNy41MTg3MDcsMTcuNTE3NDc0MzggLTM3LjE4OTQ1MiwzOC4zODY3MTkgMC4zMjc2OTMsMjAuODcyMjczIDE3LjUxNDQ3MywzNy41MjY1MDEgMzguMzg2NzIyLDM3LjE5NzI2NSBsIDExNS44NjUyMywtMS44NDU3MDMgMTg3LjIyMDcsNDA5LjQyOTY4NCAtNjIuNjYwOTEsMTI0LjkzOTQ5IGMgLTIyLjcxMjgyLDQ3LjMwMjg0IDguMTkzNzEsMTEwLjY4MTYxIDY2LjQ4NTk3LDExMC42ODE2MSBsIDU3NC41MzA0MSwxLjE3MzgzIGMgMjAuODczNDksMC4wMzY1IDM3LjgyNDQ5LC0xNi44NTUwNCAzNy44NjEyOSwtMzcuNzI4NTIgMC4wMzcsLTIwLjg3MDQzIC0xNi44NTAyLC0zNy44MjAxNiAtMzcuNzIwNjYsLTM3Ljg2MTMzIGwgLTU3MS41OTU3MSwtMS4wNjI1IDU4LjYzNDc3LC0xMjIuMDA5NzYgMzY4Ljk3NjU2LC0wLjgxODM2IGMgMTMuNjI4NTUsLTAuMDI5OCAyNi4xODU4LC03LjM5MzkxIDMyLjg2NTI0LC0xOS4yNzM0NCBsIDE4MS40NzQ2LC0zMjIuOTM1NTUgYyAxMC4yMjc1LC0xOC4xOTcyNyAzLjc2NjIsLTQxLjI0MDE0IC0xNC40MzE2LC01MS40NjY3OSAtOC43MzkzLC00LjkxMDA4IC0xOS4wNzEyLC02LjE0NzMgLTI4LjcyMjcsLTMuNDM5NDYgLTkuNjUwNCwyLjcwNTk5IC0xNy44MzA4Niw5LjEzNDMgLTIyLjc0MjE4LDE3Ljg3MTEgTCA4MjMuMDYyNSw0MjYuNDkwMjMgNDc2Ljc2OTUzLDQyNy4yNTU4NiAyODIuMDIxNDgsMS4zODg2NzE5IEMgMjc1Ljc3OTMsLTEyLjI1Njk0MSAyNjIuMDU2NDUsLTIwLjkxODAzIDI0Ny4wNTI3MywtMjAuNjgxNjQxIFoiLz4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QxIiBpZD0icmVjdDE3NzYzIiBkPSJtIDEyMy4yNjYsNDEuMzc2NjU5IGggMjIuMzQ2MDcgYyAyLjI4OTIzLDAgNC4xMzIyLDEuODQyOTYyIDQuMTMyMiw0LjEzMjIwMiB2IDYyLjA2ODMyOSBoIC0xNi42Mzk3IEwgMTE5LjEzMzgsNzYuMzQyMDc5IFYgNDUuNTA4ODYxIGMgMCwtMi4yODkyNCAxLjg0Mjk2LC00LjEzMjIwMiA0LjEzMjIsLTQuMTMyMjAyIHoiLz4mI3hhOyAgICA8cGF0aCBjbGFzcz0ic3QyIiBpZD0icmVjdDE3NzYzLTUiIGQ9Im0gMTY0LjQ5MTk4LDI3LjEwNjAwOSBoIDIxLjQ2MTA5IGMgMi42OTc5LDAgNC44Njk4NSwyLjE3MTk1MSA0Ljg2OTg1LDQuODY5ODQ1IFYgMTA3LjU3NzE5IEggMTU5LjYyMjEzIFYgMzEuOTc1ODU0IGMgMCwtMi42OTc4OTQgMi4xNzE5NSwtNC44Njk4NDUgNC44Njk4NSwtNC44Njk4NDUgeiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDAiIGlkPSJyZWN0MTc3NjMtMyIgZD0ibSAyMDUuNTAxOTYsMC4zNDUwODY2MyBoIDIxLjEwMTMyIGMgMi44NTIwNiwwIDUuMTQ4MTIsMi4yOTYwNjI3NyA1LjE0ODEyLDUuMTQ4MTIyNzcgViA3MS44Nzc5MzEgTCAyMTEuNzk4NjUsMTA3LjU3NzE5IEggMjAwLjM1Mzg0IFYgNS40OTMyMDk0IGMgMCwtMi44NTIwNiAyLjI5NjA2LC01LjE0ODEyMjc3IDUuMTQ4MTIsLTUuMTQ4MTIyNzcgeiIvPiYjeGE7ICAgIDxwYXRoIGNsYXNzPSJzdDIiIHRyYW5zZm9ybT0ibWF0cml4KDAuMjY0NTgzMzMsMCwwLDAuMjY0NTgzMzMsMC4xOTQzMDM0Miw1LjQzMTE5MjkpIiBkPSJtIDg5MC4yNTE5NSw3NTYuNzc1MzkgYSA5OC44NjQ5ODYsOTguODY0OTg2IDAgMCAwIC05OC44NjUyMyw5OC44NjUyMyA5OC44NjQ5ODYsOTguODY0OTg2IDAgMCAwIDk4Ljg2NTIzLDk4Ljg2NTI0IDk4Ljg2NDk4Niw5OC44NjQ5ODYgMCAwIDAgOTguODY1MjQsLTk4Ljg2NTI0IDk4Ljg2NDk4Niw5OC44NjQ5ODYgMCAwIDAgLTk4Ljg2NTI0LC05OC44NjUyMyB6IG0gLTQ4OS41MzMyLDAuNDg4MjggYSA5OC44NjQ5ODYsOTguODY0OTg2IDAgMCAwIC05OC44NjUyMyw5OC44NjUyNCA5OC44NjQ5ODYsOTguODY0OTg2IDAgMCAwIDk4Ljg2NTIzLDk4Ljg2NTIzIDk4Ljg2NDk4Niw5OC44NjQ5ODYgMCAwIDAgOTguODY1MjMsLTk4Ljg2NTIzIDk4Ljg2NDk4Niw5OC44NjQ5ODYgMCAwIDAgLTk4Ljg2NTIzLC05OC44NjUyNCB6Ii8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'secret manager': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc1MzkzNyIgdmVyc2lvbj0iMS4xIiB2aWV3Qm94PSIwIDAgMTc1LjE2MDY0NDUzMTI1IDEwNC4yNzczNTEzNzkzOTQ1MyIgaGVpZ2h0PSIxMDQuMjc3MzUxMzc5Mzk0NTMiIHdpZHRoPSIxNzUuMTYwNjQ0NTMxMjUiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+CS5zdDB7ZmlsbDojNDI4NWY0O308L3N0eWxlPgkmI3hhOyAgPHBhdGggY2xhc3M9InN0MCIgZD0ibSAxMjguNTY5MSwzNC4xMTUyMzYgdiAxMi45Nzg1MTYgbCAtMTIuMzM3ODksLTQuMzgwODYgLTIuNTA5NzcsNy4wNjgzNiAxMi41NDEwMiw0LjQ1MzEyNSAtOC41NjA1NSwxMS40MzE2NCA2LjAwMTk2LDQuNDk2MDk0IDguNTk5NjEsLTExLjQ4MDQ2OSA4LjQ5NDE0LDExLjQ2NDg0NCA2LjAyNzM0LC00LjQ2NDg0NCAtOC40NzI2NiwtMTEuNDMzNTkzIDEyLjY0MDYzLC00LjQ2Njc5NyAtMi41LC03LjA3MDMxMyAtMTIuNDIzODMsNC4zOTA2MjUgViAzNC4xMTUyMzYgWiBtIC00NC43NzY4NzIsMCB2IDEyLjk3ODUxNiBsIC0xMi4zMzc4OTEsLTQuMzgwODYgLTIuNTA5NzY1LDcuMDY4MzYgMTIuNTQxMDE1LDQuNDUzMTI1IC04LjU2MDU0NywxMS40MzE2NCA2LjAwMTk1Myw0LjQ5NjA5NCA4LjU5OTYxLC0xMS40ODA0NjkgOC40OTQxNCwxMS40NjQ4NDQgNi4wMjczNDcsLTQuNDY0ODQ0IC04LjQ3MjY1OSwtMTEuNDMzNTkzIDEyLjY0MDYyOSwtNC40NjY3OTcgLTIuNSwtNy4wNzAzMTMgLTEyLjQyMzgzMiw0LjM5MDYyNSBWIDM0LjExNTIzNiBaIG0gLTQ0Ljc3Njg1LDAgdiAxMi45Nzg1MTYgbCAtMTIuMzM3ODkxLC00LjM4MDg2IC0yLjUwOTc2NSw3LjA2ODM2IDEyLjU0MTAxNSw0LjQ1MzEyNSAtOC41NjA1NDcsMTEuNDMxNjQgNi4wMDE5NTMsNC40OTYwOTQgOC41OTk2MSwtMTEuNDgwNDY5IDguNDk0MTQsMTEuNDY0ODQ0IDYuMDI3MzQ0LC00LjQ2NDg0NCAtOC40NzI2NTYsLTExLjQzMzU5MyAxMi42NDA2MjUsLTQuNDY2Nzk3IC0yLjUsLTcuMDcwMzEzIC0xMi40MjM4MjgsNC4zOTA2MjUgViAzNC4xMTUyMzYgWiBNIDE3NS4xNjA2NCwxMGUtNyBWIDEwNC4yNzczNCBoIC0zNy4yNzY4MiBjIC0xLjIwODU3LDAgLTIuMDAyNDgsLTAuNjIzNTQgLTIuMDAyNDgsLTEuODY2MzQgdiAtOS45MjcyMzggYyAwLC0xLjE0ODI1IDAuNzE1OTYsLTEuNzA2NDIgMi4wMDI0OCwtMS43MDY0MiBoIDIzLjc3NjgyIFYgMTMuNSBoIC0yMy45NDQ5OCBjIC0xLjQwODU1LDAgLTEuOTUxNTEsLTAuNzUyMzE3IC0xLjk1MTUxLC0yLjA3NDQ4MiBWIDEuODQyNzI2IGMgMCwtMS4yNjU5NzEgMC42OTgwOCwtMS44NDI3MjUgMS45NTE1MSwtMS44NDI3MjUgeiBNIDAsMCB2IDEwNC4yNzczNSBoIDM3LjI3NjgxNCBjIDEuMjA4NTcxLDAgMi4wMDI0ODMsLTAuNjIzNTQgMi4wMDI0ODMsLTEuODY2MzQgdiAtOS45MjcyMzggYyAwLC0xLjE0ODI1IC0wLjcxNTk1NywtMS43MDY0MiAtMi4wMDI0ODMsLTEuNzA2NDIgSCAxMy41IFYgMTMuNDk5OTk5IGggMjMuOTQ0OTczIGMgMS40MDg1NTIsMCAxLjk1MTUxMSwtMC43NTIzMTcgMS45NTE1MTEsLTIuMDc0NDgyIFYgMS44NDI3MjUgQyAzOS4zOTY0ODQsMC41NzY3NTQgMzguNjk4NDEsMCAzNy40NDQ5NzMsMCBaIi8+JiN4YTs8L3N2Zz4=',
        'security command center': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE3LjE4MDAwMDMwNTE3NTc4IiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMTcuMTgwMDAwMzA1MTc1NzggMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik05LjkgNC44NWE1LjIzIDUuMjMgMCAwIDEgMy43NSAzLjc1aDMuNTNWMy4yNEw5LjkgMHpNMy41MiA4LjYxYTUuMjIgNS4yMiAwIDAgMSAzLjc1LTMuNzVWMEwwIDMuMjR2NS4zN3pNNy4yOCAxNWE1LjIzIDUuMjMgMCAwIDEtMy43NS0zLjc1SC4yMkExMiAxMiAwIDAgMCA3LjI4IDIwem02LjM4LTMuNzVBNS4yMyA1LjIzIDAgMCAxIDkuOTEgMTV2NWExMiAxMiAwIDAgMCA3LjA1LTguNzV6Ii8+JiN4YTsJPGNpcmNsZSBjbGFzcz0ic3QxIiBjeD0iOC41OSIgY3k9IjkuOTIiIHI9IjIuNjMiLz4mI3hhOzwvc3ZnPg==',
        'security key enforcement': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE1LjcyMyIgaGVpZ2h0PSIxOS45ODYiIHZpZXdCb3g9IjAgMCAxNS43MjMgMTkuOTg2Ij4mI3hhOwk8cGF0aCBkPSJNMy42MzQgMTQuNTg2di0zLjc1YzAtLjE1LS4yOS0uMzQtLjQ5LS40M2E1LjQ2IDUuNDYgMCAxIDEgNy40NC02LjgzIDUuNCA1LjQgMCAwIDEtMi43MyA2Ljc5LjgyLjgyIDAgMCAwLS41NC45djguNzJoLTMuNjh2LTEuNzVILjAyNHYtMy42NXptMy42NC05LjExYTEuODIgMS44MiAwIDEgMC0zLjY0LS4wNiAxLjgzIDEuODMgMCAwIDAgMS44IDEuODVoMGExLjg0IDEuODQgMCAwIDAgMS44My0xLjc5eiIgZmlsbD0iIzQyODVmNCIvPiYjeGE7CTxwYXRoIGQ9Ik0xNS4zNzQgMy41NzZhNS40NCA1LjQ0IDAgMCAwLTYuMzItMy40NCA1LjQ0IDUuNDQgMCAwIDEgMS4xMyAxMC4yMy44NC44NCAwIDAgMC0uNTUuOXY4LjcyaDIuNDN2LTguNzFhLjgzLjgzIDAgMCAxIC41NS0uOSA1LjQgNS40IDAgMCAwIDIuNzYtNi44eiIgZmlsbD0iIzY2OWRmNiIvPiYjeGE7PC9zdmc+',
        'speech-to-text': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE4IiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMTggMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwk8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik04IDBoMnYyMEg4ek00IDZoMnY4SDR6bTggMGgydjhoLTJ6TTAgM2gydjE0SDB6bTE2IDBoMnYxNGgtMnoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QxIiBkPSJNOCAwaDJ2MTBIOHpNNCA2aDJ2NEg0em04IDBoMnY0aC0yek0wIDNoMnY3SDB6bTE2IDBoMnY3aC0yeiIvPiYjeGE7PC9zdmc+',
        'standard network tier': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjQyNC4wMDEwMzc1OTc2NTYyNSIgaGVpZ2h0PSIyMTMuOTk4Mzk3ODI3MTQ4NDQiIHZpZXdCb3g9Ii0wLjAwMDAyMDQ4Mjg0MTEzNjk4MTczMyAwIDQyNC4wMDEwMzc1OTc2NTYyNSAyMTMuOTk4Mzk3ODI3MTQ4NDQiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTk5LjQzMSA0Ni44NTRsLjM3NC4yODkgMTA1Ljc1OCA4My4yMDhhNDIuMDggNDIuMDggMCAwIDEgNC43MTUtLjM4OWwuNzg5LS4wMTNjMTcuNDExLS4wMDQgMzMuMDE4IDEwLjc1OCAzOS4yMjMgMjcuMDQ5czEuNzIxIDM0LjcyNS0xMS4yNzEgNDYuMzMzYTQxLjkzIDQxLjkzIDAgMCAxLTQ3LjI1MyA1Ljk1NiA0Mi4wNCA0Mi4wNCAwIDAgMS0yMi40NDQtNDEuNTcxbC4wNTYtLjUxOS0uMDI2LS4wM0w4Ny43IDU4Ljk3NmMtOS40ODEtMTIuNTYyLS41NzUtMjEuNDg2IDExLjczLTEyLjEyM3ptMzA2LjgzOCAxMjcuNzI2YzkuNzkzIDAgMTcuNzMyIDcuOTQ5IDE3LjczMiAxNy43NTVzLTcuOTM5IDE3Ljc1NS0xNy43MzIgMTcuNzU1LTE3LjczMi03Ljk0OS0xNy43MzItMTcuNzU1IDcuOTM5LTE3Ljc1NSAxNy43MzItMTcuNzU1ek02MC4yNDEgNjguNzk3bDIwLjQyMyAyOC4zMmEyMTcuMTYgMjE3LjE2IDAgMCAwLTQ2LjkyIDk3LjM5OSAxNy4wNCAxNy4wNCAwIDAgMS0xMS4yODggMTIuOTYxYy01LjgyMyAxLjk2NC0xMi4yNTEuNjMzLTE2LjgxOS0zLjQ4MmExNy4wNiAxNy4wNiAwIDAgMS01LjIyOS0xNi4zOGM4LjgxNy00NC4zMDUgMjkuNDk5LTg1LjM3NiA1OS44MzMtMTE4LjgxN3ptMzIyLjc2MiA0MS4zMDhjOS43OTMgMCAxNy43MzIgNy45NDkgMTcuNzMyIDE3Ljc1NXMtNy45MzkgMTcuNzU1LTE3LjczMiAxNy43NTUtMTcuNzMyLTcuOTQ5LTE3LjczMi0xNy43NTUgNy45MzktMTcuNzU1IDE3LjczMi0xNy43NTV6bS00MS42MjgtNTUuMDk0YzkuNzkzIDAgMTcuNzMyIDcuOTQ5IDE3LjczMiAxNy43NTVzLTcuOTM5IDE3Ljc1NS0xNy43MzIgMTcuNzU1LTE3LjczMi03Ljk0OS0xNy43MzItMTcuNzU1IDcuOTM5LTE3Ljc1NSAxNy43MzItMTcuNzU1em0tNTcuNzkyLTM4Ljk3OWM5Ljc5MyAwIDE3LjczMiA3Ljk0OSAxNy43MzIgMTcuNzU1cy03LjkzOSAxNy43NTUtMTcuNzMyIDE3Ljc1NS0xNy43MzItNy45NDktMTcuNzMyLTE3Ljc1NSA3LjkzOS0xNy43NTUgMTcuNzMyLTE3Ljc1NXptLTEzMy4wNzQtNC4zMjdjOS43OTMgMCAxNy43MzIgNy45NDkgMTcuNzMyIDE3Ljc1NXMtNy45MzkgMTcuNzU1LTE3LjczMiAxNy43NTUtMTcuNzMyLTcuOTQ5LTE3LjczMi0xNy43NTUgNy45MzktMTcuNzU1IDE3LjczMi0xNy43NTV6TTIxNy4zNTcgMGM5Ljc5MyAwIDE3LjczMiA3Ljk0OSAxNy43MzIgMTcuNzU1UzIyNy4xNSAzNS41MSAyMTcuMzU3IDM1LjUxcy0xNy43MzItNy45NDktMTcuNzMyLTE3Ljc1NVMyMDcuNTY0IDAgMjE3LjM1NyAweiIgZmlsbD0iIzQyODVmNCIvPiYjeGE7PC9zdmc+',
        'text-to-speech': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwLjAwMDQ2MzQ4NTcxNzc3MyIgaGVpZ2h0PSIxNi42MzE1MTU1MDI5Mjk2ODgiIHZpZXdCb3g9IjAgMC4wMDAyNDE0MDk2NTI1MTcxNzcxNiAyMC4wMDA0NjM0ODU3MTc3NzMgMTYuNjMxNTE1NTAyOTI5Njg4Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPiYjeGE7CS5zdDB7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qxe2ZpbGw6IzQyODVmNDt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNLjAxIDMuMzA2aDYuNjR2MS42N0guMDF6bS0uMDEgMTBoMCA5LjE3di0xLjY3SDB6bTAtNC4xN2g0LjE4SDEwbC0xLjY3LTEuNjZIMi41MSAweiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xMCA1LjM4NmEuNDIuNDIgMCAwIDEgLjQyLS4zNi40MS40MSAwIDAgMSAuNDEuMzZ2OS4xOGEyLjA5IDIuMDkgMCAwIDAgMi42MSAyIDIuMTYgMi4xNiAwIDAgMCAxLjU2LTIuMTFWMi4wNjZhLjQuNCAwIDAgMSAuMTktLjQuNDEuNDEgMCAwIDEgLjQ1IDAgLjQuNCAwIDAgMSAuMTkuNHY5LjE2YTIuMDcgMi4wNyAwIDAgMCAuODEgMS42NCAyIDIgMCAwIDAgMS44LjM3IDIuMTYgMi4xNiAwIDAgMCAxLjU2LTIuMTJ2LTIuOGgtMS42N3YyLjkyYS40LjQgMCAwIDEtLjE5LjQuNDEuNDEgMCAwIDEtLjQ1IDAgLjQuNCAwIDAgMS0uMTktLjR2LTkuMTdhMi4wOSAyLjA5IDAgMCAwLTIuNjEtMiAyLjE2IDIuMTYgMCAwIDAtMS41NiAyLjEzdjEyLjM3YS40LjQgMCAwIDEtLjE5LjQuNDEuNDEgMCAwIDEtLjQ1IDAgLjQuNCAwIDAgMS0uMTktLjR2LTkuMTdhMi4wNyAyLjA3IDAgMCAwLTQuMTEtLjM2IDIuNCAyLjQgMCAwIDAtLjA1LjQ2djJMMTAgOS4xMzZ6Ii8+JiN4YTs8L3N2Zz4=',
        'traffic director': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjM3OC45OTYwMDM2OTA5NDU4IiBoZWlnaHQ9IjM3My40ODg4MDkyODIxODgyNCIgdmlld0JveD0iMCAwIDEwMC4yNzYwMDA5NzY1NjI1IDk4LjgxOTAwNzg3MzUzNTE2Ij4mI3hhOzxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTs8L3N0eWxlPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDAiIGQ9Ik0xNC42MTQgMjQuNzc1TDAgMzQuNzA5bDE0LjYxNCA5LjkzM1YzOS45NWMzLjU0NSAxLjQwMyA3LjcwNCAzLjY1OSAxMS4yMjYgNi44NDggNS4yMjQgNC43MyA5LjIzNSAxMS4yIDkuMjM1IDIwLjk2NXYxMS41MzJoMTBWNjcuNzYyYzAtMTIuNjQ0LTUuNjcxLTIyLjE3NS0xMi41MjMtMjguMzc5LTUuOTI5LTUuMzY4LTEyLjU5Mi04LjQ3LTE3LjkzNy0xMC4wMjR6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTU0Ljg4NiAxOC41NTR2NjYuMDIxaC00LjUzNWwxMC4xOSAxNC4yNDQgMTAuMTktMTQuMjQ0aC01Ljg0NlYxOC41NTR6TTM5Ljk2MSAwbC05LjcwNSAxMy45NThoNC44MTl2NjUuMzM2aDEwVjEzLjk1N2g0LjU5MXoiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNNTQuODg2IDE4LjU1NHYxMi45YzAgMTMuNDY0IDYuNzE5IDIzLjE0OCAxNC4wNTIgMjkuMTI1IDUuOTI1IDQuODI5IDEyLjE0NiA3LjUxIDE2LjQxNCA4Ljg3NnY0LjcyMmwxNC45MjQtOS41NzEtMTQuOTI0LTkuNTcxdjMuNzI1Yy0zLjA0My0xLjI3OC02Ljc3LTMuMjIxLTEwLjA5OC01LjkzMy01LjY5OC00LjY0NC0xMC4zNjktMTEuMTEtMTAuMzY5LTIxLjM3M3YtMTIuOXoiLz4mI3hhOzwvc3ZnPg==',
        'translation api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE4IiB2aWV3Qm94PSIwIDAgMjAgMTgiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O2ZpbGwtcnVsZTpldmVub2RkfSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTE1LjkxIDcuMmgtMS44MkwxMCAxOGgxLjgybDEtMi43aDQuMzJsMSAyLjdIMjB6bS0yLjM5IDYuM0wxNSA5LjZsMS40OCAzLjl6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwLjc5IDExLjc3TDguNDggOS41MWgwYTE1LjYyIDE1LjYyIDAgMCAwIDMuNC01LjkxaDIuNjdWMS44SDguMThWMEg2LjM2djEuOEgwdjEuNzloMTAuMTVhMTQuMDYgMTQuMDYgMCAwIDEtMi44OCA0LjgyIDE0LjU1IDE0LjU1IDAgMCAxLTIuMS0zSDMuMzVhMTYgMTYgMCAwIDAgMi43MSA0LjFMMS40NCAxNGwxLjI5IDEuMyA0LjU0LTQuNSAyLjgzIDIuOHoiLz4mI3hhOzwvc3ZnPg==',
        'vertex ai': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGlkPSJzdmc1IiB2ZXJzaW9uPSIxLjEiIHZpZXdCb3g9IjAgMCAyMzkuNzA4MjUgMjc0Ljg2MzI4IiBoZWlnaHQ9IjI3NC44NjMyOG1tIiB3aWR0aD0iMjM5LjcwODI1bW0iPiYjeGE7ICAmI3hhOyAgPGRlZnMgaWQ9ImRlZnMyIi8+JiN4YTsgIDxnIHRyYW5zZm9ybT0idHJhbnNsYXRlKC02Ni42ODYzNjEsNjAuMjU5NzY2KSIgaWQ9ImxheWVyMSI+JiN4YTsgICAgPGcgc3R5bGU9Im9wYWNpdHk6MC45OSIgaWQ9InBhdGg4NjkiLz4mI3hhOyAgICA8ZyBzdHlsZT0ib3BhY2l0eTowLjk5IiBpZD0icGF0aDg2OS0yIi8+JiN4YTsgICAgPGcgc3R5bGU9Im9wYWNpdHk6MC45OSIgaWQ9InBhdGg4NjktMyIvPiYjeGE7ICAgIDxnIHN0eWxlPSJvcGFjaXR5OjAuOTkiIGlkPSJwYXRoODY5LTEiLz4mI3hhOyAgICA8ZyBzdHlsZT0ib3BhY2l0eTowLjk5IiBpZD0icGF0aDg2OS04Ii8+JiN4YTsgICAgPGcgc3R5bGU9Im9wYWNpdHk6MC45OSIgaWQ9InBhdGg4NzEiPiYjeGE7ICAgICAgPHBhdGggaWQ9InBhdGgzMzU3IiBkPSJtIDc3LjE4Njc3NSwxMTAuODgyNTIgOTQuMjM5Njk1LDY5Ljc0NTc1IiBzdHlsZT0iY29sb3I6IzAwMDAwMDtmaWxsOiMwMDgwMDA7c3Ryb2tlLXdpZHRoOjIxO3N0cm9rZS1saW5lY2FwOnJvdW5kOy1pbmtzY2FwZS1zdHJva2U6bm9uZSIvPiYjeGE7ICAgIDwvZz4mI3hhOyAgICA8ZyBzdHlsZT0ib3BhY2l0eTowLjk5IiBpZD0icGF0aDg3MyIvPiYjeGE7ICAgIDxwYXRoIGQ9Im0gMTUzLjA4MTIsMTA5LjAzNTY4IGMgMCw2LjEyMDQ3IC00Ljk2MTYyLDExLjA4MjA5IC0xMS4wODIwOSwxMS4wODIwOSAtNi4xMjA0NywwIC0xMS4wODIwOCwtNC45NjE2MiAtMTEuMDgyMDgsLTExLjA4MjA5IDAsLTYuMTIwNDYgNC45NjE2MiwtMTEuMDgyMDgyIDExLjA4MjA4LC0xMS4wODIwODcgNi4xMjA0NywtMTBlLTcgMTEuMDgyMDksNC45NjE2MTcgMTEuMDgyMDksMTEuMDgyMDg3IHogbSAwLC05Mi41MTMzODEgYyAwLDYuMTIwNDY5IC00Ljk2MTYyLDExLjA4MjA5IC0xMS4wODIwOSwxMS4wODIwODkgLTYuMTIwNDcsLTVlLTYgLTExLjA4MjA4LC00Ljk2MTYyNCAtMTEuMDgyMDgsLTExLjA4MjA4OSAwLC02LjEyMDQ2NSA0Ljk2MTYxLC0xMS4wODIwODQ2IDExLjA4MjA4LC0xMS4wODIwODk2IDYuMTIwNDcsLTZlLTcgMTEuMDgyMDksNC45NjE2MjA2IDExLjA4MjA5LDExLjA4MjA4OTYgeiBtIDAsLTMyLjkyMTY4MyBjIDAsNi4xMjA0NjkgLTQuOTYxNjIsMTEuMDgyMDkwNSAtMTEuMDgyMDksMTEuMDgyMDg5OSAtNi4xMjA0NywtNWUtNiAtMTEuMDgyMDgsLTQuOTYxNjIzOSAtMTEuMDgyMDgsLTExLjA4MjA4OTkgMCwtNi4xMjA0NjUgNC45NjE2MSwtMTEuMDgyMDg0IDExLjA4MjA4LC0xMS4wODIwODkgNi4xMjA0NywtMTBlLTcgMTEuMDgyMDksNC45NjE2MiAxMS4wODIwOSwxMS4wODIwODkgeiBNIDEwOC43NDE4MSw3Ni43MTgwMSBjIDAsNi4xMjA0NjkgLTQuOTYxNjIsMTEuMDgyMDg5IC0xMS4wODIwODksMTEuMDgyMDg5IC02LjEyMDQ2OSwwIC0xMS4wODIwODksLTQuOTYxNjIgLTExLjA4MjA4OSwtMTEuMDgyMDg5IDAsLTYuMTIwNDY5IDQuOTYxNjIsLTExLjA4MjA4OSAxMS4wODIwODksLTExLjA4MjA4OSA2LjEyMDQ2OSwwIDExLjA4MjA4OSw0Ljk2MTYyIDExLjA4MjA4OSwxMS4wODIwODkgeiBtIDAsLTMyLjY4MDYyNiBjIDAsNi4xMjA0NjkgLTQuOTYxNjIsMTEuMDgyMDg5IC0xMS4wODIwODksMTEuMDgyMDg5IC02LjEyMDQ2OSwwIC0xMS4wODIwODksLTQuOTYxNjIgLTExLjA4MjA4OSwtMTEuMDgyMDg5IDAsLTYuMTIwNDY5IDQuOTYxNjIsLTExLjA4MjA4OSAxMS4wODIwODksLTExLjA4MjA4OSA2LjEyMDQ2OSwwIDExLjA4MjA4OSw0Ljk2MTYyIDExLjA4MjA4OSwxMS4wODIwODkgeiBtIDAsLTMyLjY3ODI0MyBjIDAsNi4xMjA0NjkgLTQuOTYxNjIsMTEuMDgyMDkgLTExLjA4MjA4OSwxMS4wODIwOSAtNi4xMjA0NjksMCAtMTEuMDgyMDksLTQuOTYxNjIxIC0xMS4wODIwODksLTExLjA4MjA5IDAsLTYuMTIwNDY4OCA0Ljk2MTYyLC0xMS4wODIwODkwNyAxMS4wODIwODksLTExLjA4MjA4OTA3IDYuMTIwNDY5LDAgMTEuMDgyMDg5LDQuOTYxNjIwMjcgMTEuMDgyMDg5LDExLjA4MjA4OTA3IHogTSAxNDIsMzcuNzc5Mjk3IGMgLTUuNzk4OTksMCAtMTAuNSw0LjcwMTAxIC0xMC41LDEwLjUgdiAyOC45OTQxNCBjIDAsNS43OTg5OSA0LjcwMTAxLDEwLjUgMTAuNSwxMC41IDUuNzk4OTksMCAxMC41LC00LjcwMTAxIDEwLjUsLTEwLjUgdiAtMjguOTk0MTQgYyAwLC01Ljc5ODk5IC00LjcwMTAxLC0xMC41IC0xMC41LC0xMC41IHogbSAtOC45ZS00LDEwLjUwMDM3NyBWIDc3LjI3MzY5MSBNIDk3LjY2MDE1NiwtNjAuMjU5NzY2IGMgLTUuNzk4OTksMCAtMTAuNSw0LjcwMTAxIC0xMC41LDEwLjUgdiAyOC45OTQxNDEgYyAwLDUuNzk4OTkgNC43MDEwMSwxMC41IDEwLjUsMTAuNSA1Ljc5ODk5NCwyZS02IDEwLjUwMDAwNCwtNC43MDEwMDkgMTAuNTAwMDA0LC0xMC41IHYgLTI4Ljk5NDE0MSBjIDAsLTUuNzk4OTkxIC00LjcwMTAxLC0xMC41MDAwMDIgLTEwLjUwMDAwNCwtMTAuNSB6IG0gLTQuMzVlLTQsMTAuNDk5NzY1IHYgMjguOTk0MDE3IE0gNzUuNjM0NzY2LDEwMC40OTgwNSBjIC0yLjc1NDE5MSwwLjQxMTQ4IC01LjIzMjExOSwxLjkwMDIxIC02Ljg4ODY3Miw0LjEzODY3IC0zLjQ0ODg3NCw0LjY2MTU3IC0yLjQ2NjAyNCwxMS4yMzYzNSAyLjE5NTMxMiwxNC42ODU1NSBsIDk0LjIzODI4NCw2OS43NDYwOSAxMi43ODYwNCwtMTYuNjY2NTkgLTk0LjUzMjEzNiwtNjkuOTU4NDEgYyAtMi4yMzg2OTksLTEuNjU3MTYgLTUuMDQ0MTAxLC0yLjM1NjkzIC03Ljc5ODgyOCwtMS45NDUzMSB6IiBzdHlsZT0iY29sb3I6IzAwMDAwMDtvcGFjaXR5OjAuOTk7ZmlsbDojYjVjYmY5O2ZpbGwtb3BhY2l0eToxO3N0cm9rZS13aWR0aDoyMTtzdHJva2UtbGluZWNhcDpyb3VuZDtzdHJva2UtbGluZWpvaW46cm91bmQ7LWlua3NjYXBlLXN0cm9rZTpub25lIiBpZD0icGF0aDE4NDAtNSIvPiYjeGE7ICAgIDxwYXRoIGQ9Im0gMTk3LjM5Mjc2LDE0MS45NzM2NiBjIDAsNi4xMjA0NyAtNC45NjE2MiwxMS4wODIwOSAtMTEuMDgyMDksMTEuMDgyMDkgLTYuMTIwNDcsMCAtMTEuMDgyMDksLTQuOTYxNjIgLTExLjA4MjA5LC0xMS4wODIwOSAwLC02LjEyMDQ3IDQuOTYxNjIsLTExLjA4MjA5IDExLjA4MjA5LC0xMS4wODIwOSA2LjEyMDQ3LDAgMTEuMDgyMDksNC45NjE2MiAxMS4wODIwOSwxMS4wODIwOSB6IG0gMCwtOTIuNzI1NTg2IGMgMCw2LjEyMDQ2OSAtNC45NjE2MiwxMS4wODIwOSAtMTEuMDgyMDksMTEuMDgyMDg5IC02LjEyMDQ3LDFlLTYgLTExLjA4MjA5LC00Ljk2MTYyIC0xMS4wODIwOSwtMTEuMDgyMDg5IDAsLTYuMTIwNDcgNC45NjE2MiwtMTEuMDgyMDkxIDExLjA4MjA5LC0xMS4wODIwOSA2LjEyMDQ3LC0xZS02IDExLjA4MjA5LDQuOTYxNjIgMTEuMDgyMDksMTEuMDgyMDkgeiBtIDAsLTMyLjg1NDQ1OCBjIDAsNi4xMjA0NjkgLTQuOTYxNjIsMTEuMDgyMDkgLTExLjA4MjA5LDExLjA4MjA4OSAtNi4xMjA0NywxMGUtNyAtMTEuMDgyMDksLTQuOTYxNjIgLTExLjA4MjA5LC0xMS4wODIwODkgMCwtNi4xMjA0NjkgNC45NjE2MiwtMTEuMDgyMDkwMyAxMS4wODIwOSwtMTEuMDgyMDg5NyA2LjEyMDQ3LC02ZS03IDExLjA4MjA5LDQuOTYxNjIwNyAxMS4wODIwOSwxMS4wODIwODk3IHogbSAxMDAuMDI5MTEsODQuMDA2Nzc0IGMgLTIuNzU1MTcsLTAuNDA1MDA0IC01LjU1ODM4LDAuMzAxMDcgLTcuNzkyOTYsMS45NjI4OSBsIC05NC43NDYxLDcwLjQzNzUgMTIuNTI5MywxNi44NTM1MiA5NC43NDYwOSwtNzAuNDM3NSBjIDQuNjU0MTIsLTMuNDU5NzggNS42MjIxNSwtMTAuMDM3NDggMi4xNjIxMSwtMTQuNjkxNDEgLTEuNjYxMzYsLTIuMjM1NTMgLTQuMTQyODcsLTMuNzE5MzcgLTYuODk4NDQsLTQuMTI1IHogTSAxODYuMzEwNTUsNzAuODY3MTg3IGMgLTUuNzk4OTksMCAtMTAuNSw0LjcwMTAxIC0xMC41LDEwLjUgdiAyOC45OTQxNDMgYyAwLDUuNzk4OTkgNC43MDEwMSwxMC41IDEwLjUsMTAuNSA1Ljc5ODk5LDAgMTAuNSwtNC43MDEwMSAxMC41LC0xMC41IFYgODEuMzY3MTg3IGMgMCwtNS43OTg5OSAtNC43MDEwMSwtMTAuNSAtMTAuNSwtMTAuNSB6IG0gMS4yZS00LDEwLjUwMDgyNyB2IDI4Ljk5NDAxNiIgc3R5bGU9ImNvbG9yOiMwMDAwMDA7b3BhY2l0eTowLjk5O2ZpbGw6Izc2OWVmNTtmaWxsLW9wYWNpdHk6MTtzdHJva2Utd2lkdGg6MjE7c3Ryb2tlLWxpbmVjYXA6cm91bmQ7c3Ryb2tlLWxpbmVqb2luOnJvdW5kOy1pbmtzY2FwZS1zdHJva2U6bm9uZSIgaWQ9InBhdGgxODQwLTMiLz4mI3hhOyAgICA8cGF0aCBkPSJtIDE4Ni4zNDU3LDE3MC42ODE2NCBjIC0xMi4wNDU3LDAgLTIxLjk2MDkzLDkuOTE1MjQgLTIxLjk2MDkzLDIxLjk2MDk0IDAsMTIuMDQ1NyA5LjkxNTIzLDIxLjk2MDk0IDIxLjk2MDkzLDIxLjk2MDk0IDEyLjA0NTcsMCAyMS45NjA5NCwtOS45MTUyNCAyMS45NjA5NCwtMjEuOTYwOTQgMCwtMTIuMDQ1NyAtOS45MTUyNCwtMjEuOTYwOTQgLTIxLjk2MDk0LC0yMS45NjA5NCB6IG0gMCwxNCBjIDQuNDc5NTUsMCA3Ljk2MDk0LDMuNDgxMzkgNy45NjA5NCw3Ljk2MDk0IDAsNC40Nzk1NSAtMy40ODEzOSw3Ljk2MDk0IC03Ljk2MDk0LDcuOTYwOTQgLTQuNDc5NTQsMCAtNy45NjA5MywtMy40ODEzOSAtNy45NjA5MywtNy45NjA5NCAwLC00LjQ3OTU1IDMuNDgxMzksLTcuOTYwOTQgNy45NjA5MywtNy45NjA5NCB6IE0gMjg2LjE2MTM3LDc2Ljc5MTAwOCBBIDExLjA4MjA4OSwxMS4wODIwODkgMCAwIDEgMjc1LjA3OTI4LDg3Ljg3MzA5NyAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIDI2My45OTcyLDc2Ljc5MTAwOCAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIDI3NS4wNzkyOCw2NS43MDg5MTkgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAyODYuMTYxMzcsNzYuNzkxMDA4IFogbSAwLC0zMy4xNDU0MzUgYSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIC0xMS4wODIwOSwxMS4wODIwODkgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAtMTEuMDgyMDgsLTExLjA4MjA4OSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIDExLjA4MjA4LC0xMS4wODIwOSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIDExLjA4MjA5LDExLjA4MjA5IHogbSAwLC05Mi40NjgyMjQgYSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIC0xMS4wODIwOSwxMS4wODIwOSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIC0xMS4wODIwOCwtMTEuMDgyMDkgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAxMS4wODIwOCwtMTEuMDgyMDg5IDExLjA4MjA4OSwxMS4wODIwODkgMCAwIDEgMTEuMDgyMDksMTEuMDgyMDg5IHogbSAtNDQuMjEzNjIsMzIuNTU3NzE2IGEgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAtMTEuMDgyMDksMTEuMDgyMDg5OSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIC0xMS4wODIwOSwtMTEuMDgyMDg5OSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIDExLjA4MjA5LC0xMS4wODIwODkgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAxMS4wODIwOSwxMS4wODIwODkgeiBtIDAsOTIuNTM1NDQzIGEgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAtMTEuMDgyMDksMTEuMDgyMDg5IDExLjA4MjA4OSwxMS4wODIwODkgMCAwIDEgLTExLjA4MjA5LC0xMS4wODIwODkgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAxMS4wODIwOSwtMTEuMDgyMDkgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAxMS4wODIwOSwxMS4wODIwOSB6IG0gMCwzMi44ODIzMTIgYSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIC0xMS4wODIwOSwxMS4wODIwOSAxMS4wODIwODksMTEuMDgyMDg5IDAgMCAxIC0xMS4wODIwOSwtMTEuMDgyMDkgMTEuMDgyMDg5LDExLjA4MjA4OSAwIDAgMSAxMS4wODIwOSwtMTEuMDgyMDkzIDExLjA4MjA4OSwxMS4wODIwODkgMCAwIDEgMTEuMDgyMDksMTEuMDgyMDkzIHogbSAzMy4xMzIzMywtMTM2LjU4ODM2NyBhIDEwLjUsMTAuNSAwIDAgMCAtMTAuNSwxMC41IHYgMjguOTk0MTQxIGEgMTAuNSwxMC41IDAgMCAwIDEwLjUsMTAuNSAxMC41LDEwLjUgMCAwIDAgMTAuNSwtMTAuNSB2IC0yOC45OTQxNDEgYSAxMC41LDEwLjUgMCAwIDAgLTEwLjUsLTEwLjUgeiBtIC04ZS00LDEwLjUwMDc1OSBWIDEyLjA1OTIyOSBNIDIzMC44NjUyMyw1LjI0MDIzNDQgYSAxMC41LDEwLjUgMCAwIDAgLTEwLjUsMTAuNDk5OTk5NiB2IDI4Ljk5NDE0MSBhIDEwLjUsMTAuNSAwIDAgMCAxMC41LDEwLjUgMTAuNSwxMC41IDAgMCAwIDEwLjUsLTEwLjUgViAxNS43NDAyMzQgYSAxMC41LDEwLjUgMCAwIDAgLTEwLjUsLTEwLjQ5OTk5OTYgeiBtIDQuMmUtNCwxMC40OTk0MzA2IHYgMjguOTk0MDE3IiBzdHlsZT0iY29sb3I6IzAwMDAwMDtvcGFjaXR5OjAuOTk7ZmlsbDojNTk4NmYyO2ZpbGwtb3BhY2l0eToxO3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjpyb3VuZDstaW5rc2NhcGUtc3Ryb2tlOm5vbmUiIGlkPSJwYXRoMTg0MC04Ii8+JiN4YTsgIDwvZz4mI3hhOzwvc3ZnPg==',
        'video intelligence api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjE5Ljk4OTk5OTc3MTExODE2NCIgaGVpZ2h0PSIxNCIgdmlld0JveD0iMCAwIDE5Ljk4OTk5OTc3MTExODE2NCAxNCI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzY2OWRmNjt9JiN4YTsJLnN0MXtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPHBhdGggY2xhc3M9InN0MCIgZD0iTTEwLjI3IDIuMzNoMi4wNXYxLjMzSDkuNEw3LjA3IDBIMHY0LjMzaDEuOTlMMy4yNSAyaDIuNTdsLjg2IDEuMzNINC4xMUwyLjg1IDUuNjZIMHYyLjU5aDIuODVsMS4yNiAyLjQxaDIuNTdMNS44MiAxMkgzLjI1TDEuOTkgOS42NkgwVjE0aDcuMDdsMi4zMy0zLjY3aDIuOTJ2MS4zM2gtMi4wNUw4LjggMTRoNS41MlY3LjY2SDcuOTFMNy4wOCA5SDUuMjRMNi41IDcgNS4yNCA1aDEuODRsLjggMS4zM2g2LjQ0VjBIOC44eiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xNS45OSAxMC4xMWw0IDIuOTVWMS4xbC00IDIuOTF6Ii8+JiN4YTs8L3N2Zz4=',
        'virtual private cloud': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIiB2aWV3Qm94PSIwIDAgMjAgMjAiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM0Mjg1ZjQ7fSYjeGE7CS5zdDF7ZmlsbDojNjY5ZGY2O30mI3hhOwkuc3Qye2ZpbGw6I2FlY2JmYTt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMTQgMGg2djZoLTZ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE3IDBoM3Y2aC0zeiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDIiIGQ9Ik0xNCAxNGg2djZoLTZ6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MSIgZD0iTTE3IDE0aDN2NmgtM3oiLz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QyIiBkPSJNMCAwaDZ2NkgweiIvPiYjeGE7CTxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0zIDBoM3Y2SDN6Ii8+JiN4YTsJPHBhdGggY2xhc3M9InN0MiIgZD0iTTAgMTRoNnY2SDB6Ii8+JiN4YTsJPGcgY2xhc3M9InN0MSI+JiN4YTsJCTxwYXRoIGQ9Ik0zIDE0aDN2Nkgzek02IDJoOHYySDZ6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik02IDE2aDh2Mkg2ek0xNiA2aDJ2OGgtMnpNMiA2aDJ2OEgyeiIvPiYjeGE7CTwvZz4mI3hhOwk8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMiA2aDJ2Mkgyem0xNCAwaDJ2MmgtMnpNNiAyaDJ2Mkg2em0wIDE0aDJ2Mkg2eiIvPiYjeGE7PC9zdmc+',
        'vision api': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE2IiB2aWV3Qm94PSIwIDAgMjAgMTYiPiYjeGE7CTxzdHlsZSB0eXBlPSJ0ZXh0L2NzcyI+JiN4YTsJLnN0MHtmaWxsOiM2NjlkZjY7fSYjeGE7CS5zdDF7ZmlsbDojYWVjYmZhO30mI3hhOwkuc3Qye2ZpbGw6IzQyODVmNDt9JiN4YTsJPC9zdHlsZT4mI3hhOwk8ZyBjbGFzcz0ic3QwIj4mI3hhOwkJPHBhdGggZD0iTTEwIDE2TDAgOGg0bDYgNC45OXoiLz4mI3hhOwkJPHBhdGggZD0iTTIwIDhsLTEwIDh2LTMuMDFMMTYgOHoiLz4mI3hhOwk8L2c+JiN4YTsJPGcgY2xhc3M9InN0MSI+JiN4YTsJCTxwYXRoIGQ9Ik0xMCAzLjAxTDQgOEgwbDEwLTh6Ii8+JiN4YTsJCTxwYXRoIGQ9Ik0yMCA4TDEwIDB2My4wMUwxNiA4eiIvPiYjeGE7CTwvZz4mI3hhOwk8Y2lyY2xlIGNsYXNzPSJzdDIiIGN4PSIxMCIgY3k9IjgiIHI9IjIiLz4mI3hhOzwvc3ZnPg==',
        'web security scanner': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnY9Imh0dHBzOi8vdmVjdGEuaW8vbmFubyIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE3LjI3OTk5ODc3OTI5Njg3NSIgdmlld0JveD0iMCAwIDIwIDE3LjI3OTk5ODc3OTI5Njg3NSI+JiN4YTsJPHN0eWxlIHR5cGU9InRleHQvY3NzIj4mI3hhOwkuc3Qwe2ZpbGw6IzQyODVmNDt9JiN4YTsJLnN0MXtmaWxsOiM2NjlkZjY7fSYjeGE7CTwvc3R5bGU+JiN4YTsJPGNpcmNsZSBjbGFzcz0ic3QwIiBjeD0iOS40NCIgY3k9IjguMTQiIHI9IjIuOTciLz4mI3hhOwk8ZyBjbGFzcz0ic3QxIj4mI3hhOwkJPGNpcmNsZSBjeD0iMi4wMiIgY3k9IjcuNDMiIHI9IjIuMDIiLz4mI3hhOwkJPGNpcmNsZSBjeD0iMTIuNTIiIGN5PSIxNS4yNiIgcj0iMi4wMiIvPiYjeGE7CQk8cGF0aCBkPSJNMTcuNTcuODRBMi40MyAyLjQzIDAgMSAwIDIwIDMuMjcgMi40MyAyLjQzIDAgMCAwIDE3LjU3Ljg0em0wIDMuOGExLjM3IDEuMzcgMCAxIDEgMS4zNi0xLjM3aDBhMS4zNyAxLjM3IDAgMCAxLTEuMzYgMS4zN3oiLz4mI3hhOwkJPHBhdGggZD0iTTE2LjIgMy4zMkE4LjI5IDguMjkgMCAwIDAgMTEuMTQgMGwtLjI4IDEuMzRhNi45NSA2Ljk1IDAgMSAxLTguMjIgNS4zOCA2Ljg4IDYuODggMCAwIDEgMS44Ny0zLjQ3bC0xLTFhOC4zMSA4LjMxIDAgMSAwIDEzLjM4IDIuMiAxLjM2IDEuMzYgMCAwIDEtLjY5LTEuMTN6Ii8+JiN4YTsJPC9nPiYjeGE7PC9zdmc+',
        'workflows': 'data:image/svg+xml,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIiB3aWR0aD0iMTkuNTEwMDAwMjI4ODgxODM2IiBoZWlnaHQ9IjE5LjUwMDAxOTA3MzQ4NjMyOCIgdmlld0JveD0iMy4zODYwNTk0MzI4NDE2NDhlLTggMCAxOS41MTAwMDAyMjg4ODE4MzYgMTkuNTAwMDE5MDczNDg2MzI4Ij4mI3hhOwk8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgkuc3Qwe2ZpbGw6IzQyODVmNDt9CS5zdDF7ZmlsbDojNjY5ZGY2O30JLnN0MntmaWxsOiNhZWNiZmE7fQk8L3N0eWxlPgkmI3hhOyAgPHBhdGggY2xhc3M9InN0MCIgZD0iTTE3LjI2IDE3LjgxaC0uN3YtMS41aC43YS43Ni43NiAwIDAgMCAuNzUtLjc1di00LjMxYS43Ni43NiAwIDAgMC0uNzUtLjc1aC0zLjYxVjloMy42MWEyLjI1IDIuMjUgMCAwIDEgMi4yNSAyLjI1djQuMzFhMi4yNSAyLjI1IDAgMCAxLTIuMjUgMi4yNXptLTcuOTUgMGgtNC45di0xLjVoNC45eiIvPiYjeGE7ICA8cGF0aCBjbGFzcz0ic3QxIiBkPSJNNS44OCAxMC41SDIuMjZBMi4yNSAyLjI1IDAgMCAxIC4wMSA4LjI1VjMuOTRhMi4yNSAyLjI1IDAgMCAxIDIuMjUtMi4yNWgxdjEuNWgtMWEuNzUuNzUgMCAwIDAtLjc1Ljc1djQuMzFhLjc2Ljc2IDAgMCAwIC43NS43NWgzLjYyeiIvPiYjeGE7ICA8cGF0aCBjbGFzcz0ic3QwIiBkPSJNMTUuMDYgMy4xOUg5LjU4di0xLjVoNS40OHoiLz4mI3hhOyAgPHBhdGggY2xhc3M9InN0MiIgZD0iTTYuMzkgMS42OVYuMTloLTNhMS4xMyAxLjEzIDAgMCAwLTEuMTMgMS4xMnYyLjI1YTEuMTMgMS4xMyAwIDAgMCAxLjEzIDEuMTNoM3YtMS41SDMuNzZ2LTEuNXoiLz4mI3hhOyAgPHBhdGggY2xhc3M9InN0MSIgZD0iTTEwLjUxIDEuMzF2Mi4yNWExLjEzIDEuMTMgMCAwIDEtMS4xMiAxLjEzaC0zdi0xLjVoMi42MnYtMS41SDYuMzlWLjE5aDNhMS4xMiAxLjEyIDAgMCAxIDEuMTIgMS4xMnoiLz4mI3hhOyAgPHBhdGggY2xhc3M9InN0MiIgZD0iTTE3LjA3IDQuODhhMi40NCAyLjQ0IDAgMSAxIDIuNDQtMi40NCAyLjQ1IDIuNDUgMCAwIDEtMi40NCAyLjQ0em0wLTMuMzhhLjk0Ljk0IDAgMSAwIC45NC45NC45NC45NCAwIDAgMC0uOTQtLjk0eiIvPiYjeGE7ICA8ZyBjbGFzcz0ic3QyIiBmaWxsPSIjYWVjYmZhIj4mI3hhOyAgICA8dXNlIHhsaW5rOmhyZWY9IiNCIi8+JiN4YTsgICAgPHBhdGggZD0iTTEzLjEyIDE2LjMydi0xLjVoLTNBMS4xMyAxLjEzIDAgMCAwIDkgMTUuOTV2Mi4yNWExLjEyIDEuMTIgMCAwIDAgMS4xMiAxLjEyaDN2LTEuNUgxMC41di0xLjV6Ii8+JiN4YTsgIDwvZz4mI3hhOyAgPHBhdGggY2xhc3M9InN0MSIgZD0iTTE3LjI1IDE1Ljk1djIuMjVhMS4xMyAxLjEzIDAgMCAxLTEuMTMgMS4xMmgtM3YtMS41aDIuNjR2LTEuNWgtMi42NHYtMS41aDNhMS4xNCAxLjE0IDAgMCAxIDEuMTMgMS4xM3oiLz4mI3hhOyAgPHBhdGggY2xhc3M9InN0MiIgZD0iTTkuNzYgOVY3LjVoLTNhMS4xMyAxLjEzIDAgMCAwLTEuMTMgMS4xMnYyLjI1QTEuMTMgMS4xMyAwIDAgMCA2Ljc2IDEyaDN2LTEuNUg3LjEzVjl6Ii8+JiN4YTsgIDxwYXRoIGNsYXNzPSJzdDEiIGQ9Ik0xMy44OCA4LjYydjIuMjVBMS4xMyAxLjEzIDAgMCAxIDEyLjc2IDEyaC0zdi0xLjVoMi42MlY5SDkuNzZWNy41aDNhMS4xMiAxLjEyIDAgMCAxIDEuMTIgMS4xMnoiLz4mI3hhOyAgPGRlZnM+JiN4YTsgICAgPHBhdGggaWQ9IkIiIGQ9Ik0yLjQ1IDE5LjVhMi40NCAyLjQ0IDAgMSAxIDIuNDMtMi40NCAyLjQ0IDIuNDQgMCAwIDEtMi40MyAyLjQ0em0wLTMuMzhhLjk0Ljk0IDAgMSAwIC45My45NC45NC45NCAwIDAgMC0uOTMtLjk0eiIvPiYjeGE7ICA8L2RlZnM+JiN4YTs8L3N2Zz4=',
    }

    GCP_SHAPES = {
        # Networking, Content Delivery & Gateways
        "application gateway": "mxgraph.gcp2.cloud_load_balancing",
        "application gateways": "mxgraph.gcp2.cloud_load_balancing",
        "load balancer": "mxgraph.gcp2.cloud_load_balancing",
        "front door": "mxgraph.gcp2.cdn",
        "front doors": "mxgraph.gcp2.cdn",
        "cloud cdn": "mxgraph.gcp2.cdn",
        "bastion": "mxgraph.gcp2.identity_aware_proxy",
        "bastions": "mxgraph.gcp2.identity_aware_proxy",
        "identity-aware proxy": "mxgraph.gcp2.identity_aware_proxy",
        "iap": "mxgraph.gcp2.identity_aware_proxy",
        "beyondcorp": "mxgraph.gcp2.identity_aware_proxy",
        "dns zones": "mxgraph.gcp2.cloud_dns",
        "cloud dns": "mxgraph.gcp2.cloud_dns",
        "firewalls": "mxgraph.gcp2.cloud_armor",
        "cloud armor": "mxgraph.gcp2.cloud_armor",
        "cloud armor enterprise": "mxgraph.gcp2.cloud_armor",
        "vpn gateway": "mxgraph.gcp2.cloud_vpn",
        "cloud interconnect": "mxgraph.gcp2.cloud_interconnect",
        "interconnect": "mxgraph.gcp2.cloud_interconnect",
        "partner interconnect": "mxgraph.gcp2.cloud_interconnect",
        "dedicated interconnect": "mxgraph.gcp2.cloud_interconnect",
        "cloud nat": "mxgraph.gcp2.cloud_nat",
        "nat gateway": "mxgraph.gcp2.cloud_nat",
        "router": "mxgraph.gcp2.cloud_router",
        "cloud router": "mxgraph.gcp2.cloud_router",
        "api gateway": "mxgraph.gcp2.api_gateway",
        "cloud endpoints": "mxgraph.gcp2.cloud_endpoints",

        # Compute, Containers & Orchestration
        "virtual machine": "mxgraph.gcp2.compute_engine",
        "virtual machines": "mxgraph.gcp2.compute_engine",
        "vm": "mxgraph.gcp2.compute_engine",
        " vm": "mxgraph.gcp2.compute_engine",
        "vm ": "mxgraph.gcp2.compute_engine",
        "gce": "mxgraph.gcp2.compute_engine",
        "kubernetes services": "mxgraph.gcp2.kubernetes_engine",
        "gke": "mxgraph.gcp2.kubernetes_engine",
        "anthos": "mxgraph.gcp2.anthos",
        "anthos service mesh": "mxgraph.gcp2.anthos",
        "distributed cloud": "mxgraph.gcp2.anthos",
        "container instances": "mxgraph.gcp2.cloud_run",
        "container services": "mxgraph.gcp2.cloud_run",
        "cloud run": "mxgraph.gcp2.cloud_run",
        "app engine": "mxgraph.gcp2.app_engine",
        "cloud composer": "mxgraph.gcp2.cloud_composer",
        "compliance orchestrator": "mxgraph.gcp2.cloud_composer",
        "cloud functions": "mxgraph.gcp2.cloud_functions",
        "cloud function": "mxgraph.gcp2.cloud_functions",
        "functions": "mxgraph.gcp2.cloud_functions",

        # Databases & Storage
        "data lake": "mxgraph.gcp2.cloud_storage",
        "data lake storage": "mxgraph.gcp2.cloud_storage",
        "storage account": "mxgraph.gcp2.cloud_storage",
        "cloud storage": "mxgraph.gcp2.cloud_storage",
        "gcs": "mxgraph.gcp2.cloud_storage",
        "persistent disk": "mxgraph.gcp2.persistent_disk",
        "persistent disks": "mxgraph.gcp2.persistent_disk",
        "filestore": "mxgraph.gcp2.filestore",
        "sql database": "mxgraph.gcp2.cloud_sql",
        "sql managed instance": "mxgraph.gcp2.cloud_sql",
        "cloud sql": "mxgraph.gcp2.cloud_sql",
        "cloud spanner": "mxgraph.gcp2.cloud_spanner",
        "spanner database": "mxgraph.gcp2.cloud_spanner",
        "cloud bigtable": "mxgraph.gcp2.cloud_bigtable",
        "firestore": "mxgraph.gcp2.firestore",
        "datastore": "mxgraph.gcp2.firestore",
        "memorystore": "mxgraph.gcp2.memorystore",

        # Analytics, Dashboards & Data Integration
        "synapse analytics": "mxgraph.gcp2.bigquery",
        "bigquery": "mxgraph.gcp2.bigquery",
        "event hubs": "mxgraph.gcp2.pubsub",
        "pubsub": "mxgraph.gcp2.pubsub",
        "workflows": "mxgraph.gcp2.workflows",
        "looker": "mxgraph.gcp2.looker",
        "looker / data studio": "mxgraph.gcp2.looker",
        "dataplex": "mxgraph.gcp2.dataplex",
        "data governance": "mxgraph.gcp2.dataplex",
        "dataproc": "mxgraph.gcp2.dataproc",
        "dataflow": "mxgraph.gcp2.dataflow",
        "cloud data fusion": "mxgraph.gcp2.cloud_data_fusion",
        "data fusion": "mxgraph.gcp2.cloud_data_fusion",

        # AI / Machine Learning (Vertex AI Framework)
        "ai studio": "mxgraph.gcp2.vertex_ai",
        "machine learning studio workspaces": "mxgraph.gcp2.vertex_ai",
        "azure openai": "mxgraph.gcp2.vertex_ai",
        "cognitive services": "mxgraph.gcp2.vertex_ai",
        "vertex ai platform": "mxgraph.gcp2.vertex_ai",
        "vertex ai pipelines": "mxgraph.gcp2.vertex_ai",
        "vertex ai model registry": "mxgraph.gcp2.vertex_ai",
        "vertex explainable ai": "mxgraph.gcp2.vertex_ai",
        "vertex ai monitoring": "mxgraph.gcp2.vertex_ai",
        "vertex ai endpoint": "mxgraph.gcp2.vertex_ai",

        # Security, Operations, IAM & Compliance
        "active directory": "mxgraph.gcp2.iam",
        "entra id": "mxgraph.gcp2.iam",
        "cloud iam": "mxgraph.gcp2.cloud_iam",
        "access control": "mxgraph.gcp2.iam",
        "key vault": "mxgraph.gcp2.cloud_key_management_service",
        "cloud kms": "mxgraph.gcp2.cloud_key_management_service",
        "encryption": "mxgraph.gcp2.cloud_key_management_service",
        "secret manager": "mxgraph.gcp2.secret_manager",
        "cloud asset inventory": "mxgraph.gcp2.cloud_asset_inventory",
        "cloud resource manager": "mxgraph.gcp2.cloud_resource_manager",
        "web security scanner": "mxgraph.gcp2.web_security_scanner",
        "security command center": "mxgraph.gcp2.security_command_center",
        "defender": "mxgraph.gcp2.security_command_center",
        "sentinel": "mxgraph.gcp2.security_command_center",
        "chronicle": "mxgraph.gcp2.security_command_center",
        "chronicle siem": "mxgraph.gcp2.security_command_center",
        "monitor": "mxgraph.gcp2.cloud_monitoring",
        "cloud monitoring": "mxgraph.gcp2.cloud_monitoring",
        "activity log": "mxgraph.gcp2.cloud_logging",
        "cloud logging": "mxgraph.gcp2.cloud_logging",
        "diagnostic settings": "mxgraph.gcp2.cloud_logging",
        "operations suite": "mxgraph.gcp2.cloud_monitoring",
        "stackdriver": "mxgraph.gcp2.cloud_monitoring",
        "cloud trace": "mxgraph.gcp2.cloud_monitoring",
        "cloud profiler": "mxgraph.gcp2.cloud_monitoring",
        "error reporting": "mxgraph.gcp2.cloud_monitoring",
        "cloud dlp": "mxgraph.gcp2.sensitive_data_protection",
        "sensitive data protection": "mxgraph.gcp2.sensitive_data_protection",
        "user": "mxgraph.gcp2.user",
    }
        
    AZURE_CONTAINERS = {
        "virtual network": "img/lib/azure2/networking/Virtual_Networks.svg",
        "vnet": "img/lib/azure2/networking/Virtual_Networks.svg",
        "subnet": "img/lib/azure2/networking/Subnet.svg",
        "resource group": "img/lib/azure2/general/Resource_Groups.svg",
        "management group": "img/lib/azure2/general/Management_Groups.svg",
        "region": "img/lib/azure2/general/Region_Management.svg",
        "availability zone": "img/lib/azure2/general/Availability_Zones.svg",
        "landing zone": "img/lib/azure2/general/Region_Management.svg",
        "purview": "img/lib/azure2/databases/Azure_Purview_Accounts.svg",
        "devops": "img/lib/azure2/devops/Azure_DevOps.svg",
        "machine learning workspace": "img/lib/azure2/ai_machine_learning/Machine_Learning.svg",
        "azure machine learning": "img/lib/azure2/ai_machine_learning/Machine_Learning.svg",
        "private endpoint": "img/lib/azure2/other/Private_Endpoints.svg",
        "private endpoints": "img/lib/azure2/other/Private_Endpoints.svg",
        "power bi": "img/lib/azure2/power_platform/PowerBI.svg",
        "powerbi": "img/lib/azure2/power_platform/PowerBI.svg",
        "data lake storage": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "data lake storage gen1": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",
        "data lake storage gen2": "img/lib/azure2/storage/Data_Lake_Storage_Gen1.svg",  # corrected
        "azure defender": "img/lib/azure2/security/Microsoft_Defender_for_Cloud.svg",
        "defender": "img/lib/azure2/security/Microsoft_Defender_for_Cloud.svg",
    }

    AWS_CONTAINERS = {
        # "aws4group:<grIcon>:<strokeColor>" is a special marker (not a
        # real style fragment) detected in _apply_shape_mappings. Verified
        # against multiple independent real-world .drawio files: AWS4
        # containers use a native vector group shape
        # (shape=mxgraph.aws4.group;grIcon=...;) -- NOT an image path.
        # There is no confirmed img/lib/aws4/... equivalent for these.
        "aws cloud": "aws4group:mxgraph.aws4.group_aws_cloud_alt:#232F3E",
        "vpc": "aws4group:mxgraph.aws4.group_vpc2:#8C4FFF",
        "public subnet": "aws4group:mxgraph.aws4.group_security_group:#7AA116",
        "private subnet": "aws4group:mxgraph.aws4.group_security_group:#147EBA",
        "subnet": "aws4group:mxgraph.aws4.group_security_group:#7AA116",
        "region": "aws4group:mxgraph.aws4.group_region:#00A4A6",
        "availability zone": "aws4group:mxgraph.aws4.group_availability_zone:#232F3E",
    }

    GCP_CONTAINERS = {
        # "gcpcontainer:<fillColor>" is a special marker (not a real style
        # fragment) detected in _apply_shape_mappings. Verified directly
        # against an authentic Google Cloud Architecture Diagramming Tool
        # export (user-provided ground truth, a complete resource-hierarchy
        # legend): GCP containers are plain borderless colored rectangles
        # (shape=rect;strokeColor=none;...;fillColor=<pastel>;), NOT any
        # img/lib/gcp2/... image (that convention was unverified guesswork;
        # this is confirmed-real). Colors are consistent across repeated
        # occurrences of the same concept in the source file (e.g. "Zone"
        # is #FFF3E0 everywhere), confirming this is Google's own
        # systematic color-per-concept convention, not arbitrary.
        "project zone": "gcpcontainer:#F6F6F6",
        "cloud service provider": "gcpcontainer:#F6F6F6",
        "logical grouping": "gcpcontainer:#E3F2FD",
        "vpc network": "gcpcontainer:#E3F2FD",
        "vpc ": "gcpcontainer:#E3F2FD",
        "zone": "gcpcontainer:#FFF3E0",
        "subnetwork": "gcpcontainer:#EDE7F6",
        "subnet": "gcpcontainer:#EDE7F6",
        "kubernetes cluster": "gcpcontainer:#FCE4EC",
        "gke cluster": "gcpcontainer:#FCE4EC",
        "pod": "gcpcontainer:#E8F5E9",
        "account": "gcpcontainer:#E8EAF6",
        "region": "gcpcontainer:#ECEFF1",
        "firewall": "gcpcontainer:#FBE9E7",
        "instance group": "gcpcontainer:#F9FBE7",
        "replica pool": "gcpcontainer:#E0F7FA",
        "managed instance group": "gcpcontainer:#E0F7FA",
    }

    PROVIDER_SHAPES = {
        "azure": AZURE_SHAPES,
        "aws": AWS_SHAPES,
        "gcp": GCP_SHAPES,
    }

    PROVIDER_CONTAINERS = {
        "azure": AZURE_CONTAINERS,
        "aws": AWS_CONTAINERS,
        "gcp": GCP_CONTAINERS,
    }

    def _fix_invalid_arrays(xml: str) -> str:
        """
        Repairs malformed <Array points="..."> tags into valid Draw.io format
        (<Array as="points"><mxPoint x=".." y=".."/>...</Array>).

        Handles BOTH coordinate formats LLMs tend to emit:
          - flat space-separated:  points="10 20 30 40"
          - comma-separated pairs: points="10,20 30,40"

        The previous implementation always split on whitespace only, so a
        comma-separated payload like "10,20 30,40" produced pts=["10,20",
        "30,40"] and then emitted <mxPoint x="10,20" y="30,40" />, which
        draw.io cannot parse as a numeric coordinate. That silently broke
        edge waypoints (edges snapping to 0,0 or vanishing) without ever
        raising an XML-validity error, since the document was still
        well-formed XML — just semantically wrong.
        """
        import re

        def _split_pairs(raw: str):
            raw = raw.strip()
            if "," in raw:
                pairs = []
                for token in raw.split():
                    parts = token.split(",")
                    if len(parts) == 2:
                        pairs.append((parts[0].strip(), parts[1].strip()))
                return pairs
            flat = raw.split()
            return list(zip(flat[0::2], flat[1::2]))

        def convert(match):
            pairs = _split_pairs(match.group(1))
            mxpts = "".join(f'<mxPoint x="{x}" y="{y}" />' for x, y in pairs)
            return '<Array as="points">' + mxpts + '</Array>'

        # Fix self-closing <Array points="..."/>
        xml = re.sub(r'<Array\s+points="([^"]+)"\s*/>', convert, xml)

        # Fix <Array points="..."></Array>
        xml = re.sub(r'<Array\s+points="([^"]+)"\s*>.*?</Array>', convert, xml, flags=re.DOTALL)

        return xml

    def _detect_provider(root) -> str:
        """
        Best-effort provider detection from mxfile/diagram attributes.
        Defaults to 'azure' if ambiguous.
        """
        mxfile = root
        provider = None

        host = mxfile.get("host", "") or ""
        agent = mxfile.get("agent", "") or ""
        meta = (host + " " + agent).lower()

        if "azure" in meta:
            provider = "azure"
        elif "aws" in meta or "amazon" in meta:
            provider = "aws"
        elif "gcp" in meta or "google" in meta:
            provider = "gcp"

        if provider is None:
            diagram = mxfile.find(".//diagram")
            if diagram is not None:
                name = (diagram.get("name", "") or "").lower()
                if "azure" in name:
                    provider = "azure"
                elif "aws" in name or "amazon" in name:
                    provider = "aws"
                elif "gcp" in name or "google" in name:
                    provider = "gcp"

        return provider or "azure"

    _AZURE_LEGACY_REF_RE = re.compile(r'shape=mxgraph\.azure\.([a-zA-Z_]+)\.([a-zA-Z0-9_]+);?')
    _AZURE_CATEGORY_FIX = {"management": "management_governance", "network": "networking"}
    _AZURE_ACRONYMS = {
        "vm", "vms", "sql", "dns", "vpn", "ip", "ai", "ml", "iot", "api", "cdn", "waf",
        "nat", "bgp", "ddos", "tls", "ssl", "mfa", "rbac", "siem", "soar", "hsm", "kms",
        "adls", "id", "sap",
    }
    # (category, name) -> (override_category_or_None, override_title). These
    # are cases where the generic acronym-aware title-casing transform isn't
    # enough -- either the real Azure icon has an entirely different display
    # name (e.g. there is no standalone "VPN Gateway" icon at all; it's
    # "Virtual Network Gateways"), is pluralized differently, or lives under
    # a different category folder than the one originally assigned. Verified
    # against draw.io's real shipped assets / the official Azure Architecture
    # Icons catalog.
    _AZURE_NAME_OVERRIDES = {
        ("ai_machine_learning", "azure_openai"): (None, "Azure_OpenAI"),
        ("security", "ms_defender_easm"): (None, "Microsoft_Defender_EASM"),
        ("storage", "data_lake_storage"): (None, "Data_Lake_Storage_Gen1"),
        ("networking", "vpn_gateway"): (None, "Virtual_Network_Gateways"),
        ("networking", "application_gateway"): (None, "Application_Gateways"),
        ("management", "network_watcher"): ("networking", "Network_Watcher"),
        ("general", "region"): (None, "Region_Management"),
        ("general", "landing_zone"): (None, "Region_Management"),
        ("networking", "virtual_network"): (None, "Virtual_Networks"),
        ("compute", "vm"): (None, "Virtual_Machine"),
        ("management", "scale"): ("compute", "VM_Scale_Sets"),
        ("security", "defender"): (None, "Microsoft_Defender_for_Cloud"),
        ("security", "azure_defender"): (None, "Microsoft_Defender_for_Cloud"),
        ("identity", "active_directory"): (None, "Azure_Active_Directory"),
        ("identity", "entra_id"): (None, "Azure_Active_Directory"),
        ("analytics", "data_factory"): (None, "Data_Factories"),
        ("ai_machine_learning", "applied_ai"): (None, "Azure_Applied_AI_Services"),
    }

    def _azure_title_segment(seg: str) -> str:
        return seg.upper() if seg.lower() in _AZURE_ACRONYMS else seg.capitalize()

    def _azure_legacy_ref_to_image(category: str, name: str) -> str:
        override = _AZURE_NAME_OVERRIDES.get((category, name))
        if override:
            override_cat, title = override
            cat = override_cat or _AZURE_CATEGORY_FIX.get(category, category)
            return f"img/lib/azure2/{cat}/{title}.svg"
        cat = _AZURE_CATEGORY_FIX.get(category, category)
        title = "_".join(_azure_title_segment(p) for p in name.split("_"))
        return f"img/lib/azure2/{cat}/{title}.svg"

    # Specific img/lib/azure2/... paths that are already in the correct
    # "image=" form syntactically, but point at a filename that doesn't
    # actually exist in draw.io's real Azure2 icon set (verified against
    # the official Azure Architecture Icons catalog). These can appear
    # already-baked into a style (e.g. from an earlier generation, or
    # hardcoded directly by an LLM) without ever going through
    # _repair_legacy_azure_shapes, since that function only catches the
    # older "shape=mxgraph.azure.<category>.<name>" pattern -- this one
    # corrects already-image-formatted but wrong references directly.
    _AZURE_KNOWN_BAD_IMAGE_PATHS = {
        "img/lib/azure2/networking/VPN_Gateway.svg": "img/lib/azure2/networking/Virtual_Network_Gateways.svg",
        "img/lib/azure2/networking/Application_Gateway.svg": "img/lib/azure2/networking/Application_Gateways.svg",
        "img/lib/azure2/networking/Virtual_Network.svg": "img/lib/azure2/networking/Virtual_Networks.svg",
        "img/lib/azure2/general/Region.svg": "img/lib/azure2/general/Region_Management.svg",
        "img/lib/azure2/management_governance/Network_Watcher.svg": "img/lib/azure2/networking/Network_Watcher.svg",
        "img/lib/azure2/compute/VM.svg": "img/lib/azure2/compute/Virtual_Machine.svg",
        "img/lib/azure2/management_governance/Scale.svg": "img/lib/azure2/compute/VM_Scale_Sets.svg",
        "img/lib/azure2/security/Defender.svg": "img/lib/azure2/security/Microsoft_Defender_for_Cloud.svg",
        "img/lib/azure2/security/Azure_Defender.svg": "img/lib/azure2/security/Microsoft_Defender_for_Cloud.svg",
        "img/lib/azure2/identity/Active_Directory.svg": "img/lib/azure2/identity/Azure_Active_Directory.svg",
        "img/lib/azure2/analytics/Data_Factory.svg": "img/lib/azure2/analytics/Data_Factories.svg",
        "img/lib/azure2/ai_machine_learning/Azure_Applied_AI.svg": "img/lib/azure2/ai_machine_learning/Azure_Applied_AI_Services.svg",
    }

    def _repair_known_bad_image_paths(style: str) -> str:
        for bad, good in _AZURE_KNOWN_BAD_IMAGE_PATHS.items():
            if bad in style:
                style = style.replace(bad, good)
        return style

    def _repair_legacy_azure_shapes(style: str) -> str:
        """
        LLM-authored XML sometimes hardcodes shape=mxgraph.azure.<category>.<name>
        directly, bypassing our AZURE_SHAPES dictionary lookup entirely. That
        nested-category vector-stencil form does not exist in draw.io's real
        stencil catalog for Azure -- verified directly against draw.io's own
        shipped assets (github.com/jgraph/drawio): the modern Azure icon set
        is distributed ONLY as raw SVGs under img/lib/azure2/, and the
        separate, real "mxgraph.azure" vector stencil set is flat (shape
        names like "AutoScale" -- no nested "networking."/"compute."
        categories). Repair any such reference in place, converting it to
        the real image style using the same category/name already chosen.
        """
        def repl(m):
            img = _azure_legacy_ref_to_image(m.group(1), m.group(2))
            return f"image;aspect=fixed;html=1;image={img};"
        return _AZURE_LEGACY_REF_RE.sub(repl, style)

    # Confirmed via real draw.io-generated files: these AWS4 identifiers
    # are genuine "dedicated shapes" used bare (strokeColor=none;
    # pointerEvents=1；no points array) rather than wrapped in the
    # resourceIcon carrier. Growing this set only from directly-confirmed
    # evidence, not guesses.
    _AWS4_DEDICATED_SHAPES = {
        "data_lake_resource_icon", "msk_amazon_msk_connect",
        "nat_gateway", "peering",
    }

    # Confirmed via a real draw.io-generated AWS icon reference file:
    # AWS4 resourceIcon-wrapped shapes use a category-specific fillColor,
    # not one universal color. Only including colors directly confirmed
    # by an example in that file -- Compute (orange, via Lambda) and
    # Networking/Analytics (purple, via VPC/NAT/Peering/EMR, which all
    # share the same confirmed hex).
    _AWS4_NETWORKING_KEYWORDS = (
        "vpc", "vpn", "nat", "peering", "network", "subnet", "route",
        "gateway", "direct_connect", "transit", "elastic_network",
        "client_vpn", "site_to_site", "cloud_wan", "emr",
    )

    def _aws4_fill_color(name: str) -> str:
        if any(k in name for k in _AWS4_NETWORKING_KEYWORDS):
            return "#8C4FFF"
        return "#ED7100"

    def _style_for_shape_ref(ref: str) -> str:
        """
        Real draw.io icon sets are NOT all addressed the same way. Verified
        directly against draw.io's own shipped assets (github.com/jgraph/drawio)
        and real-world exports:

          - Modern Azure icon set: image-only, no vector stencil namespace.
            (ref ending in .svg / starting with img/ -> rendered as an image.)
          - Confirmed-real embedded Google-sourced icons (GCP_VERIFIED_ICONS):
            a raw base64 SVG data URI, extracted directly from an authentic
            Google Cloud Architecture Diagramming Tool export -- also
            rendered as an image.
          - Modern AWS4 *individual service* icons: NOT directly renderable
            via a bare shape=mxgraph.aws4.<name> reference for MOST icons.
            They must be wrapped in the resourceIcon carrier shape, e.g.
            AWS Lambda is shape=mxgraph.aws4.resourceIcon;
            resIcon=mxgraph.aws4.lambda; -- a bare shape=mxgraph.aws4.lambda
            is not a registered stencil on its own. Confirmed (via a real
            AWS icon reference export) that the wrapper also needs the
            octagon points=[...] array and a category-specific fillColor,
            not a single universal color. Exceptions used bare: AWS4
            group/container shapes (mxgraph.aws4.group) and a confirmed
            set of "dedicated shapes" (_AWS4_DEDICATED_SHAPES).
          - GCP2 and legacy AWS3: directly renderable via a bare shape=
            reference (confirmed working real-world usage).
        """
        if ref.endswith(".svg") or ref.startswith("img/") or ref.startswith("data:image/"):
            return f"image;aspect=fixed;html=1;image={ref};"
        if ref.startswith("mxgraph.aws4."):
            name = ref[len("mxgraph.aws4."):]
            if name.startswith("group") or name in _AWS4_DEDICATED_SHAPES:
                if name in _AWS4_DEDICATED_SHAPES:
                    return (
                        "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
                        f"fillColor={_aws4_fill_color(name)};strokeColor=none;dashed=0;"
                        "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
                        f"fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape={ref};"
                    )
                return f"shape={ref};"
            return (
                "sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],"
                "[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],"
                "[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;"
                f"fontColor=#232F3E;fillColor={_aws4_fill_color(name)};strokeColor=#ffffff;"
                "dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
                f"fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon={ref};"
            )
        return f"shape={ref};"

    _AWS4_BARE_ICON_RE = re.compile(r'shape=mxgraph\.aws4\.(?!resourceIcon|productIcon|group)([a-zA-Z0-9_]+);?')

    def _repair_bare_aws4_icons(style: str) -> str:
        """
        Same idea as _repair_legacy_azure_shapes: LLM-authored XML sometimes
        hardcodes a bare shape=mxgraph.aws4.<name> directly, bypassing our
        AWS_SHAPES dictionary entirely. For most individual AWS4 service
        icons that form isn't a registered stencil, so this repairs it in
        place using the resourceIcon wrapper.

        SAFETY CHECK: AWS4 also has a second, entirely valid convention for
        "dedicated shapes" -- icons genuinely registered under their own
        bare shape=mxgraph.aws4.<name> (e.g. data_lake_resource_icon,
        msk_amazon_msk_connect) -- confirmed directly against a real
        draw.io-generated file. These use strokeColor=none;pointerEvents=1;
        and no points=[...] array, as opposed to resourceIcon-wrapped
        generic icons which use strokeColor=#ffffff and a points=[...]
        octagon array. If the existing style already carries this
        dedicated-shape signature, it's already correctly authored --
        leave it alone rather than force-wrapping it into a broken,
        double-referenced style.
        """
        if "pointerEvents=1" in style:
            return style
        def repl(m):
            return _style_for_shape_ref(f"mxgraph.aws4.{m.group(1)}")
        return _AWS4_BARE_ICON_RE.sub(repl, style)

    _IMAGE_SHAPE_COLLISION_RE = re.compile(r'^image;aspect=fixed;html=1;image=([^;]+);(.*)$')
    _BOX_STYLE_SIGNAL_RE = re.compile(r'(^|;)(shape=|fillColor=|strokeColor=|whiteSpace=wrap)')

    def _repair_image_shape_collision(style: str) -> str:
        """
        Repairs a real, observed bug: a style beginning with the bare
        "image" shape token (image;aspect=fixed;html=1;image=X;) followed
        by box-styling properties (an explicit shape=..., or fillColor/
        strokeColor/whiteSpace=wrap -- the signature of a deliberately
        styled labeled box). A bare "image" shape only ever draws the
        image itself; it silently ignores fillColor/strokeColor/
        whiteSpace=wrap entirely, and if something later also sets an
        explicit shape=..., mxGraph's last-write-wins style resolution
        cancels the image shape outright. Either way, the intended
        labeled box (background, border, wrapped label text) is lost.

        Convert to the safe, already-proven pattern used elsewhere in
        these diagrams: keep the box styling as the cell's real shape,
        and attach the icon as a small corner overlay instead
        (image=X;imageWidth=24;imageHeight=24;spacingTop=4;).
        """
        m = _IMAGE_SHAPE_COLLISION_RE.match(style)
        if not m:
            return style
        image_ref, rest = m.group(1), m.group(2)
        if not _BOX_STYLE_SIGNAL_RE.search(rest):
            return style  # genuinely just a bare image icon -- nothing to fix
        if rest and not rest.endswith(";"):
            rest += ";"
        return f"{rest}image={image_ref};imageWidth=24;imageHeight=24;spacingTop=4;"

    def _best_match(value: str, mapping: dict):
        """
        Finds the mapping entry whose key best matches `value`, using
        word-boundary matching and preferring the most specific (longest)
        key when more than one matches — regardless of the mapping's
        declaration order.

        This replaces a naive `if key in value` ordered substring scan,
        which had two concrete failure modes:
          1. Generic single-word keys (e.g. "region", "cluster", "key")
             would match as a *substring* of any longer, unrelated label
             that happened to contain that word, silently mis-mapping the
             cell (e.g. a "West US Region storage account" leaf node
             getting matched by the "region" container key). Correctness
             depended entirely on manually keeping specific keys ordered
             before generic ones in the dict literal.
          2. Padding hacks like " vm" / "vm " (to approximate a word
             boundary) failed to match a label that IS exactly "VM" with
             no surrounding whitespace at all.
        """
        candidates = []
        for key, target in mapping.items():
            key_norm = key.strip()
            if not key_norm:
                continue
            pattern = r'(?<!\w)' + re.escape(key_norm) + r'(?!\w)'
            if re.search(pattern, value):
                candidates.append((len(key_norm), target))
        if not candidates:
            return None
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        return candidates[0][1]

    def _apply_shape_mappings(raw_xml: str) -> str:
        """
        Parses the XML, detects the cloud provider, and upgrades generic
        vertex shapes to provider-specific icons and containers based on
        the cell's value text.
        """
        import xml.etree.ElementTree as ET

        try:
            tree = ET.ElementTree(ET.fromstring(raw_xml))
        except Exception as e:
            logger.error(f"Failed to parse XML for shape mapping: {e}")
            return raw_xml

        root = tree.getroot()
        provider = _detect_provider(root)
        shape_map = PROVIDER_SHAPES.get(provider, {})
        container_map = PROVIDER_CONTAINERS.get(provider, {})

        if not shape_map and not container_map:
            return raw_xml

        all_cells = root.findall(".//mxCell")

        # Repair any hardcoded fictional shape=mxgraph.azure.<category>.<name>
        # references first, regardless of detected provider or label text --
        # this fixes shapes an LLM wrote directly into the style attribute,
        # bypassing our dictionary lookup entirely.
        for cell in all_cells:
            style = cell.get("style")
            if not style:
                continue
            original = style
            if "shape=mxgraph.azure." in style:
                style = _repair_legacy_azure_shapes(style)
            if "shape=mxgraph.aws4." in style:
                style = _repair_bare_aws4_icons(style)
            if "img/lib/azure2/" in style:
                style = _repair_known_bad_image_paths(style)
            if style.startswith("image;"):
                style = _repair_image_shape_collision(style)
            if style != original:
                cell.set("style", style)

        # Structural evidence for "is this actually a container?" — a cell
        # should only be turned into a full-bleed background/group image if
        # something else genuinely nests inside it (another cell points at
        # it via parent=) or its style already declares container/group
        # semantics. Previously this was decided purely from label-text
        # substring matching, which meant an ordinary leaf service icon
        # whose label happened to contain a generic word like "region" or
        # "cluster" got swapped for a giant background container image
        # sized for a completely different kind of shape.
        parent_ids = {c.get("parent") for c in all_cells if c.get("parent")}

        # Needed for the corner-badge icon on containers (see below).
        provider_accent = {
            "azure": "#0078D4",
            "aws": "#FF9900",
            "gcp": "#4285F4",
        }.get(provider, "#666666")
        root_container_el = root.find(".//root")
        existing_ids = {c.get("id") for c in all_cells if c.get("id")}

        for cell in all_cells:
            if cell.get("vertex") != "1":
                continue

            value = (cell.get("value") or "").lower()
            if not value:
                continue

            style = cell.get("style", "") or ""
            cell_id = cell.get("id")
            already_container_like = "container=1" in style or "swimlane" in style
            has_children = cell_id is not None and cell_id in parent_ids

            # 1) Container mapping (VNet, Subnet, Region, etc.), gated on
            #    real structural evidence that this cell is a container,
            #    not just label text.
            if has_children or already_container_like:
                matched_container = _best_match(value, container_map)
                if matched_container:
                    if matched_container.startswith("aws4group:"):
                        # Confirmed-native AWS4 vector group container,
                        # verified against multiple independent real-world
                        # .drawio files. Unlike Azure (image-only) or the
                        # generic fallback below, AWS4 has a REAL vector
                        # stencil for this exact purpose -- shape=
                        # mxgraph.aws4.group;grIcon=...; -- so we use it
                        # directly instead of a plain dashed rectangle.
                        # The grIcon already renders a small badge as part
                        # of the shape itself, so no separate badge cell
                        # is needed here (unlike the image-based branch).
                        _, gr_icon, stroke_color = matched_container.split(":", 2)
                        style_parts = [
                            "points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],"
                            "[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],"
                            "[0,0.75],[0,0.5],[0,0.25]]",
                            "outlineConnect=0",
                            "gradientColor=none",
                            "html=1",
                            "whiteSpace=wrap",
                            "fontSize=12",
                            "fontStyle=0",
                            "container=1",
                            "pointerEvents=0",
                            "collapsible=0",
                            "recursiveResize=0",
                            "shape=mxgraph.aws4.group",
                            f"grIcon={gr_icon}",
                            f"strokeColor={stroke_color}",
                            "fillColor=none",
                            "verticalAlign=top",
                            "align=left",
                            "spacingLeft=30",
                            f"fontColor={stroke_color}",
                            "dashed=0",
                        ]
                        cell.set("style", ";".join(dict.fromkeys(style_parts)) + ";")
                        continue

                    if matched_container.startswith("gcpcontainer:"):
                        # Confirmed-real GCP container style, extracted
                        # directly from an authentic Google Cloud
                        # Architecture Diagramming Tool export (a complete
                        # resource-hierarchy legend). Unlike the Azure/AWS
                        # fallback below, this ISN'T a guess -- it's
                        # Google's own systematic color-per-concept
                        # convention: a plain borderless rectangle with a
                        # small top-left label, no stencil/image reference
                        # at all.
                        _, fill_color = matched_container.split(":", 1)
                        style_parts = [
                            "shape=rect",
                            "strokeColor=none",
                            "strokeWidth=2",
                            "shadow=0",
                            "gradientColor=none",
                            "fontColor=#757575",
                            "align=left",
                            "html=1",
                            "fontStyle=0",
                            "spacingTop=3",
                            f"fillColor={fill_color}",
                            "verticalAlign=top",
                            "fontSize=10",
                            "spacingLeft=10",
                            "spacing=0",
                            "container=1",
                            "collapsible=0",
                            "recursiveResize=0",
                        ]
                        cell.set("style", ";".join(dict.fromkeys(style_parts)) + ";")
                        continue

                    base_flags = []
                    if "rounded=1" in style:
                        base_flags.append("rounded=1")
                    else:
                        base_flags.append("rounded=0")

                    # IMPORTANT: this is a plain dashed rectangle, not a
                    # stretched SVG background image. Every verified
                    # real-world draw.io Azure/AWS/GCP export uses this
                    # pattern for VNet/subnet/region/resource-group
                    # containers (e.g. AWS's own "shape=mxgraph.aws4.group"
                    # container style, community Azure VNet templates) —
                    # never a "shape=image" background. Stretching a
                    # service-category SVG across an arbitrarily-sized
                    # container is a known anti-pattern: the icon's native
                    # aspect ratio rarely matches the container, and if the
                    # image path doesn't resolve in the viewer's
                    # environment the whole container renders as a broken
                    # placeholder instead of a container at all — which is
                    # exactly what was still going wrong here.
                    style_parts = [
                        "whiteSpace=wrap",
                        "html=1",
                        "fillColor=none",
                        f"strokeColor={provider_accent}",
                        "dashed=1",
                        "verticalAlign=top",
                        "align=left",
                        "fontStyle=1",
                        "spacingLeft=8",
                        "spacingTop=6",
                        "container=1",
                        "collapsible=0",
                        "recursiveResize=0",
                        "pointerEvents=0",
                    ] + base_flags

                    cell.set("style", ";".join(dict.fromkeys(style_parts)) + ";")

                    # Small, correctly-sized (non-stretched) badge icon in
                    # the container's top-right corner, reusing the same
                    # reference image — this mirrors how real AWS exports
                    # attach a small "grIcon" to group containers, instead
                    # of stretching the icon to fill the whole box.
                    if root_container_el is not None and cell_id:
                        geom = cell.find("mxGeometry")
                        try:
                            cw = float(geom.get("width")) if geom is not None else None
                        except (TypeError, ValueError):
                            cw = None
                        badge_id = f"{cell_id}_badge"
                        if cw and cw >= 60 and badge_id not in existing_ids:
                            badge = ET.Element("mxCell", {
                                "id": badge_id,
                                "value": "",
                                "style": _style_for_shape_ref(matched_container),
                                "vertex": "1",
                                "parent": cell_id,
                            })
                            ET.SubElement(badge, "mxGeometry", {
                                "x": str(cw - 34), "y": "6", "width": "28", "height": "28", "as": "geometry"
                            })
                            root_container_el.append(badge)
                            existing_ids.add(badge_id)

                    # Once treated as a container, don't also treat it as a
                    # plain service icon.
                    continue

            # 2) Service icon mapping – only if not already platform-specific
            #    (a vector stencil, an already-set azure2 image ref, or an
            #    already-set embedded data-URI icon).
            if "shape=mxgraph." in style or "image=img/lib/" in style or "image=data:image/" in style:
                continue

            matched_shape = None
            if provider == "gcp":
                # Confirmed-real, extracted directly from an authentic
                # Google Cloud Architecture Diagramming Tool export --
                # far higher confidence than the GCP_SHAPES guesses below,
                # so try this first.
                matched_shape = _best_match(value, GCP_VERIFIED_ICONS)
            if not matched_shape:
                matched_shape = _best_match(value, shape_map)
            if not matched_shape:
                continue

            is_image_ref = matched_shape.endswith(".svg") or matched_shape.startswith("img/")
            has_explicit_shape = bool(re.search(r'(^|;)shape=', style))

            if has_explicit_shape:
                # The cell already declares its own shape (e.g. shape=rect
                # with fillColor/border/rounded corners -- a deliberately
                # styled labeled box). mxGraph resolves style keys
                # last-write-wins, so prepending a competing shape
                # declaration in front of it gets silently cancelled by
                # the cell's own later shape=..., leaving no icon
                # rendered at all -- an observed real bug. Don't touch
                # the existing shape key at all.
                if is_image_ref:
                    # Attach as a small corner icon overlay instead --
                    # the same pattern already used correctly elsewhere
                    # in these diagrams (image=...;imageWidth=;imageHeight=;).
                    extra = f"image={matched_shape};imageWidth=24;imageHeight=24;spacingTop=4;"
                    if style and not style.endswith(";"):
                        style += ";"
                    cell.set("style", style + extra)
                else:
                    # A vector stencil (AWS4/GCP2/etc.) can't be layered
                    # as a simple image overlay on an existing custom
                    # shape. Attach a small companion badge cell in the
                    # corner instead -- same mechanism used for container
                    # badges above.
                    if root_container_el is not None and cell_id:
                        geom = cell.find("mxGeometry")
                        try:
                            cwidth = float(geom.get("width")) if geom is not None else None
                        except (TypeError, ValueError):
                            cwidth = None
                        badge_id = f"{cell_id}_badge"
                        if cwidth and cwidth >= 60 and badge_id not in existing_ids:
                            badge = ET.Element("mxCell", {
                                "id": badge_id,
                                "value": "",
                                "style": _style_for_shape_ref(matched_shape),
                                "vertex": "1",
                                "parent": cell_id,
                            })
                            ET.SubElement(badge, "mxGeometry", {
                                "x": str(cwidth - 30), "y": "4", "width": "24", "height": "24", "as": "geometry"
                            })
                            root_container_el.append(badge)
                            existing_ids.add(badge_id)
                continue

            # No existing shape declaration on this cell -- safe to make
            # the cell itself the icon shape directly.
            if style and not style.endswith(";"):
                style += ";"
            cell.set("style", _style_for_shape_ref(matched_shape) + style)

        try:
            return ET.tostring(root, encoding="unicode")
        except Exception as e:
            logger.error(f"Failed to serialize XML after shape mapping: {e}")
            return raw_xml

    def _validate_and_repair_mxgraph(tree):
        """
        Ensures the parsed document complies with the structural rules
        draw.io's mxGraphModel format actually requires. Violations of
        these rules are the most common reason a diagram that is
        well-formed XML still fails to render, or renders with shapes
        missing/misplaced/invisible — the failure is silent because
        ET.fromstring() only checks XML well-formedness, not any of this.

        Repairs performed (each one logged, never silent):
          - Wraps a bare <mxGraphModel> or <root> fragment in the full
            <mxfile><diagram><mxGraphModel> envelope draw.io itself writes,
            since LLMs frequently emit only the inner graph body.
          - Ensures the two mandatory scaffold cells exist: id="0" (the
            root cell) and id="1" (the default layer, parent="0"). Without
            these, draw.io can fail to open the file, or open it with
            nothing on the canvas.
          - Assigns parent="1" to any vertex/edge cell missing a parent.
          - Reparents any cell whose parent id doesn't exist to "1"
            instead of letting it silently disappear (draw.io drops cells
            with a dangling parent reference rather than erroring).
          - Injects a default 120x60 <mxGeometry> on any vertex missing
            one — a vertex cell without geometry renders as zero-size /
            invisible.

        Raises ValueError for issues that shouldn't be silently patched:
          - Duplicate mxCell ids (renaming them automatically risks
            silently breaking edge source/target references instead of
            surfacing a real problem).
          - A <diagram> using draw.io's compressed (deflate+base64) text
            content instead of inline XML — practically impossible for an
            LLM to produce correctly by hand, so treated as a hard error
            asking for uncompressed XML instead of attempting a guess-fix.

        Returns (tree, notes) where notes is a list of human-readable
        strings describing every repair that was applied, for logging.
        """
        import xml.etree.ElementTree as ET

        notes = []
        root_el = tree.getroot()

        # --- 1. Normalize the envelope --------------------------------
        if root_el.tag == "root":
            graph_model = ET.Element("mxGraphModel")
            graph_model.append(root_el)
            root_el = graph_model
            notes.append("Wrapped a bare <root> fragment in <mxGraphModel> (no wrapper was provided).")

        if root_el.tag == "mxGraphModel":
            mxfile = ET.Element("mxfile", {"host": "app.diagrams.net"})
            diagram = ET.SubElement(mxfile, "diagram", {"id": "diagram1", "name": "Page-1"})
            diagram.append(root_el)
            root_el = mxfile
            notes.append("Wrapped a bare <mxGraphModel> in <mxfile><diagram> (no file-level wrapper was provided).")

        if root_el.tag != "mxfile":
            raise ValueError(
                f"Unrecognized DrawIO document root <{root_el.tag}>; expected <mxfile>, "
                "<mxGraphModel>, or <root>."
            )

        tree = ET.ElementTree(root_el)

        diagram_el = root_el.find(".//diagram")
        if diagram_el is not None and diagram_el.text and diagram_el.text.strip() and diagram_el.find("mxGraphModel") is None:
            raise ValueError(
                "The <diagram> element contains compressed (deflate+base64) text content "
                "instead of an inline <mxGraphModel>. Regenerate using uncompressed XML "
                "directly inside <diagram>...</diagram>."
            )

        graph_model = root_el.find(".//mxGraphModel")
        if graph_model is None:
            raise ValueError("No <mxGraphModel> found inside <mxfile>/<diagram>; cannot validate structure.")

        root_container = graph_model.find("root")
        if root_container is None:
            root_container = ET.SubElement(graph_model, "root")
            notes.append("Added a missing <root> element inside <mxGraphModel>.")

        cells = root_container.findall("mxCell")

        # --- 2. Duplicate id detection (hard failure) -------------------
        seen_ids = {}
        for cell in cells:
            cid = cell.get("id")
            if cid is None:
                continue
            if cid in seen_ids:
                raise ValueError(f'Duplicate mxCell id="{cid}" found; regenerate the diagram with unique ids.')
            seen_ids[cid] = cell

        # --- 3. Mandatory scaffold cells: id="0" and id="1" -------------
        if "0" not in seen_ids:
            cell0 = ET.Element("mxCell", {"id": "0"})
            root_container.insert(0, cell0)
            seen_ids["0"] = cell0
            notes.append('Injected missing mandatory root cell id="0".')

        if "1" not in seen_ids:
            cell1 = ET.Element("mxCell", {"id": "1", "parent": "0"})
            idx = list(root_container).index(seen_ids["0"]) + 1
            root_container.insert(idx, cell1)
            seen_ids["1"] = cell1
            notes.append('Injected missing mandatory default-layer cell id="1" (parent="0").')

        # --- 4. Parent integrity ----------------------------------------
        valid_ids = set(seen_ids.keys())
        for cell in root_container.findall("mxCell"):
            cid = cell.get("id")
            if cid in ("0", "1"):
                continue
            parent = cell.get("parent")
            if not parent:
                cell.set("parent", "1")
                notes.append(f'mxCell id="{cid}" had no parent attribute; assigned parent="1".')
            elif parent not in valid_ids:
                notes.append(f'mxCell id="{cid}" referenced a missing parent "{parent}"; reparented to "1".')
                cell.set("parent", "1")

        # --- 5. Geometry integrity on vertices ----------------------------
        for cell in root_container.findall("mxCell"):
            if cell.get("vertex") == "1" and cell.find("mxGeometry") is None:
                geom = ET.SubElement(cell, "mxGeometry", {"x": "0", "y": "0", "width": "120", "height": "60"})
                geom.set("as", "geometry")
                notes.append(f'mxCell id="{cell.get("id")}" (vertex) had no <mxGeometry>; injected a default 120x60 box.')

        return tree, notes

    output_dir = os.path.join(PROJECT_ROOT, "output")
    path = os.path.join(output_dir, "cloudarch_drawio.xml")
    lock_path = os.path.join(output_dir, ".cloudarch_drawio.lock")

    _safe_sleep_from_property("modelSleep", default=0.25)

    if (
        not xml_content
        or (isinstance(xml_content, str) and xml_content.strip() == "")
    ):
        _log_agent_activity("No XML content provided to save_drawio.")
        return "INFO: No XML content provided to save_drawio, so nothing has been done."

    def acquire_lock(timeout: float = 5.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if not os.path.exists(lock_path):
                try:
                    with open(lock_path, "w", encoding="utf-8") as lf:
                        lf.write(str(os.getpid()))
                    return True
                except Exception as e:
                    logger.error(f"Failed to create lock file: {e}")
            time.sleep(0.1)
        logger.error("Timeout acquiring cloudarch_drawio lock.")
        return False

    def release_lock():
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception as e:
            logger.error(f"Failed to remove lock file: {e}")

    try:
        _log_agent_activity("Saving DrawIO XML to file...")
        os.makedirs(output_dir, exist_ok=True)

        if not acquire_lock():
            return "ERROR: Could not acquire lock for DrawIO persistence."

        raw_xml = _fix_invalid_arrays(xml_content).strip()

        try:
            import xml.etree.ElementTree as ET
            parsed_tree = ET.ElementTree(ET.fromstring(raw_xml))
        except Exception as e:
            logger.error(f"Invalid XML content: {e}")
            raw_path = os.path.join(output_dir, "cloudarch_drawio_raw.xml")
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_xml)
            return (
                "ERROR: Invalid XML provided. "
                f"Raw XML written to {raw_path}. "
                "Your last output was malformed or truncated. "
                "You MUST regenerate the architecture."
            )

        try:
            parsed_tree, repair_notes = _validate_and_repair_mxgraph(parsed_tree)
            for note in repair_notes:
                logger.warning(f"[DrawIO auto-repair] {note}")
            raw_xml = ET.tostring(parsed_tree.getroot(), encoding="unicode")
        except ValueError as e:
            logger.error(f"DrawIO structural validation failed: {e}")
            raw_path = os.path.join(output_dir, "cloudarch_drawio_raw.xml")
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_xml)
            return (
                f"ERROR: Invalid DrawIO document structure — {e} "
                f"Raw XML written to {raw_path}. "
                "You MUST regenerate the architecture."
            )

        mapped_xml = _apply_shape_mappings(raw_xml)

        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(mapped_xml)
        except Exception as e:
            logger.error(f"Invalid XML after shape mapping: {e}")
            raw_path = os.path.join(output_dir, "cloudarch_drawio_mapped_raw.xml")
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(mapped_xml)
            return (
                "ERROR: XML became invalid after shape mapping. "
                f"Raw XML written to {raw_path}. "
                "Check mapping rules or regenerate the architecture."
            )

        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as existing:
                    old_xml = existing.read().strip()
                if old_xml == mapped_xml.strip():
                    _log_agent_activity(
                        f"No changes detected; skipping write to {path}."
                    )
                    return {"SUCCESS": f"The file {path} is unchanged."}
            except Exception:
                pass

        with open(path, "w", encoding="utf-8") as f:
            f.write(mapped_xml)

        _log_agent_activity(f"Successfully saved DrawIO XML to {path}.")
        return {"SUCCESS": f"The file {path} was saved successfully."}

    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"Failed to save DrawIO XML: {error_trace}")
        return "ERROR: Failed to save DrawIO XML due to an unexpected error. Check logs for details."

    finally:
        release_lock()

def _save_raw_data_to_json(json_content) -> str:
    """
    Saves the finalized JSON to output/process_data.json.
    Includes robust repair logic for large/truncated LLM payloads.
    Uses a lock file to prevent race conditions with concurrent reads/writes.

    This is internal. The only exposed tool is persist_final_json.
    """
    output_dir = os.path.join(PROJECT_ROOT, "output")
    path = os.path.join(output_dir, "process_data.json")
    lock_path = os.path.join(output_dir, ".process_data.lock")

    _safe_sleep_from_property("modelSleep", default=0.25)
    if (
        not json_content
        or (isinstance(json_content, str) and json_content.strip() == "")
        or (isinstance(json_content, dict) and len(json_content) == 0)
    ):
        _log_agent_activity("No JSON content provided to persist_final_json.")
        return "INFO: No JSON content provided to persist_final_json, so nothing has been done."
    
    def acquire_lock(timeout: float = 5.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if not os.path.exists(lock_path):
                try:
                    with open(lock_path, "w", encoding="utf-8") as lf:
                        lf.write(str(os.getpid()))
                    return True
                except Exception as e:
                    logger.error(f"Failed to create lock file: {e}")
            time.sleep(0.1)
        logger.error("Timeout acquiring process_data lock.")
        return False

    def release_lock():
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception as e:
            logger.error(f"Failed to remove lock file: {e}")

    try:
        _log_agent_activity("Saving normalized JSON to file...")
        os.makedirs(output_dir, exist_ok=True)

        # Acquire lock before writing
        if not acquire_lock():
            return "ERROR: Could not acquire lock for JSON persistence."

        # 1. Normalize input to string
        if isinstance(json_content, dict):
            raw_str = json.dumps(json_content)
        else:
            raw_str = str(json_content).strip()

        # 2. Extract JSON using brace-balanced logic
        try:
            raw_str = _extract_json_brace_balanced(raw_str)
        except Exception as e:
            logger.error(f"Failed to extract JSON object: {e}")
            raw_path = os.path.join(output_dir, "process_data_raw.json")
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_str)
            return (
                f"ERROR: Could not extract JSON object. Raw content saved to {raw_path}."
            )

        # 3. Strip Markdown fences
        raw_str = re.sub(r'^```json\s*|```$', "", raw_str, flags=re.MULTILINE)

        # 4. Attempt validation and repair
        parsed = None
        used_repair = False
        try:
            parsed = json.loads(raw_str)
        except json.JSONDecodeError as e:
            logger.warning(
                f"Standard JSON decode failed at char {e.pos}. "
                f"Attempting structural repair..."
            )
            try:
                from json_repair import repair_json
                repaired_str = repair_json(raw_str)
                parsed = json.loads(repaired_str)
                used_repair = True
                logger.debug("JSON successfully repaired and loaded.")
            except ImportError:
                logger.error(
                    "json-repair library not found. "
                    "Install via 'pip install json-repair'. "
                )
                raw_path = os.path.join(output_dir, "process_data_raw.json")
                with open(raw_path, "w", encoding="utf-8") as rf:
                    rf.write(raw_str)
                return (
                    f"ERROR: JSONDecodeError at {e.pos} and json-repair is not installed. "
                    f"Raw JSON written to {raw_path}."
                )
            except Exception as repair_err:
                logger.error(
                    f"Repair failed: {str(repair_err)}. "
                )
                raw_path = os.path.join(output_dir, "process_data_raw.json")
                with open(raw_path, "w", encoding="utf-8") as rf:
                    rf.write(raw_str)
                return (
                    "ERROR: Critical structural failure in JSON payload. "
                    f"Raw JSON written to {raw_path}. "
                    f"Your last output was corrupted/truncated. You MUST reload the previous valid "
                    f"state using `load_master_process_json` and simplify the descriptions to fit the token limit."
                )

        if parsed is None:
            logger.error("Parsed JSON is None after validation/repair. ")
            raw_path = os.path.join(output_dir, "process_data_raw.json")
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_str)
            return (
                "ERROR: The JSON to persist was not valid. "
                f"Raw JSON written to {raw_path}. "
                f"Your last output was corrupted/truncated. You MUST reload the previous valid "
                f"state using `load_master_process_json` and simplify the descriptions to fit the token limit."
            )

        if _validate_process_json(parsed) is None:
            logger.error("Parsed JSON is invalid. ")
            raw_path = os.path.join(output_dir, "process_data_raw.json")
            with open(raw_path, "w", encoding="utf-8") as rf:
                rf.write(raw_str)
            return (
                "ERROR: The JSON to persist was not valid. "
                f"Raw JSON written to {raw_path}. "
                f"Your last output was corrupted/truncated. You MUST reload the previous valid "
                f"state using `load_master_process_json` and simplify the descriptions to fit the token limit."
            )

        # 5. Final write of clean, repaired JSON
        clean_json = json.dumps(parsed, indent=2, ensure_ascii=False)

        # Skip write if identical
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as existing:
                    old = json.load(existing)
                if _json_equal(old, parsed):
                    _log_agent_activity(
                        f"No changes detected; skipping write to {path}."
                    )
                    return {
                        "SUCCESS": f"The file {path} is unchanged."
                    }
            except Exception:
                pass  # If comparison fails, fall through to write

        with open(path, "w", encoding="utf-8") as f:
            f.write(clean_json)

        _log_agent_activity(
            f"Successfully saved JSON to {path} "
            f"({'repaired' if used_repair else 'clean'})."
        )
        return {
            "SUCCESS": f"The file {path} was saved successfully."
        }

    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"Failed to save JSON: {error_trace}")
        return "ERROR: Failed to save JSON due to an unexpected error. Check logs for details."

    finally:
        release_lock()

def _json_equal(a: dict, b: dict) -> bool:
    """Return True if two JSON objects are semantically identical."""
    try:
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    except Exception:
        return False

# ---------------------------------------------------------------------
# EXPOSED TOOL (SINGLE ENTRYPOINT FOR LLM)
# ---------------------------------------------------------------------
from google.adk.tools.tool_context import ToolContext

# process_agents/utils.py
            
def validate_process_json(json_content: Any) -> dict:
    """
    Public tool for agents to validate a process JSON structure.
    Returns a structured list of issues.
    """
    _safe_sleep_from_property("modelSleep", default=0.25)

    if not isinstance(json_content, dict):
        return {
            "valid": False,
            "issues": [
                {"location": "$", "issue": "Input is not a JSON object"}
            ]
        }

    issues = _validate_process_json(json_content)

    # None means catastrophic failure (not a dict)
    if issues is None:
        return {
            "valid": False,
            "issues": [
                {"location": "$", "issue": "Input is not a valid JSON object"}
            ]
        }

    return {
        "valid": len(issues) == 0,
        "issues": issues
    }


def persist_final_json(json_content) -> str:
    """
    Public tool for the LLM:
    - Logs that final persistence is starting.
    - Calls the internal saver with the provided JSON content.
    - Returns the final path or error message.
    """
    _safe_sleep_from_property("modelSleep", default=0.25)

    if (
        not json_content
        or (isinstance(json_content, str) and json_content.strip() == "")
        or (isinstance(json_content, dict) and len(json_content) == 0)
    ):
        _log_agent_activity("No JSON content provided to persist_final_json.")
        return "INFO: No JSON content provided to persist_final_json, so nothing has been done."

    try:
        _log_agent_activity("Starting final JSON file persistence")

        # Validate BEFORE saving
        issues = _validate_process_json(json_content)
        if issues is None:
            return "ERROR: JSON content is not a valid object."

        if len(issues) > 0:
            logger.error(f"Validation issues: {issues}")
            return json.dumps({
                "ERROR": "JSON validation failed",
                "issues": issues
            }, indent=2)

        # Save using internal writer
        result = _save_raw_data_to_json(json_content)

        if isinstance(result, str) and "No changes detected" not in result:
            _log_agent_activity(f"File persistence result: {result}")

        return result

    except Exception:
        error_trace = traceback.format_exc()
        logger.error(f"persist_final_json failed: {error_trace}")
        return "ERROR: persist_final_json encountered an unexpected failure."

# Tool to load the full process context (master + subprocesses)
def load_full_process_context() -> dict:
    """Loads master process + subprocesses directly from disk. Never returns FATAL ERROR. Returns partial data if needed."""
    context = {
        "master_process": {},
        "subprocesses": [],
        "system_status": "PARTIAL"
    }
    master_path = os.path.join(PROJECT_ROOT, "output", "process_data.json")
    if os.path.exists(master_path):
        try:
            with open(master_path, "r", encoding="utf-8") as f:
                context["master_process"] = json.load(f)
                context["system_status"] = "OK"
        except Exception as e:
            context["system_status"] = f"ERROR: {e}"
    sub_dir = os.path.join(PROJECT_ROOT, "output", "subprocesses")
    if os.path.exists(sub_dir):
        for file_path in glob.glob(os.path.join(sub_dir, "*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    context["subprocesses"].append(json.load(f))
            except Exception as e:
                logger.error(f"Error loading {file_path}: {e}")
    return context

# Tool to load iteration feedback from output/iteration_feedback.json
def load_iteration_feedback(reset_data: bool = True) -> dict:
    """
    Loads feedback, metrics, and compliance violations from iteration_feedback.json.
    Optionally resets "data" in the file to [] after reading (default True).
    This is the 'Inbox' for the Design Agent to see what other agents have requested.
    """
    _log_agent_activity("Loading iteration feedback from disk...")
    _safe_sleep_from_property("modelSleep", default=0.25)

    path = os.path.join(PROJECT_ROOT, "output", "iteration_feedback.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                json_content = f.read().strip()
                logger.debug(f"Loaded iteration feedback: {str(json_content)[:200]}")
                feedback = json.loads(json_content)
        except Exception as e:
            logger.error(f"Error loading feedback file: {e}")
            return {"status": "No feedback found", "data": []}

        if reset_data and isinstance(feedback, dict):
            try:
                feedback_reset = feedback.copy()
                feedback_reset["data"] = []
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(feedback_reset, f, indent=2)
            except Exception as e:
                logger.error(f"Error resetting feedback file: {e}")

        return feedback

    return {}

def save_iteration_feedback(feedback_data: Any):
    """
    Saves iteration feedback to disk.
    Corrects the double-nesting issue and extracts status from agent payloads.
    """
    _log_agent_activity(f"Persisting iteration feedback of type {type(feedback_data)} to disk...")
    _safe_sleep_from_property("modelSleep", default=0.25)

    output_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "iteration_feedback.json")

    # Artificial delay to prevent API burst issues in the loop
    _safe_sleep_from_property("modelSleep", default=0.25)

    # --- 1. Clean and Normalize incoming data ---
    processed_data = feedback_data
    if isinstance(feedback_data, str):
        try:
            # Basic cleanup for common LLM string issues
            normalized_str = feedback_data.replace("'", '"')
            processed_data = json.loads(normalized_str)
        except Exception:
            processed_data = feedback_data

    # --- 2. Extract internal status BEFORE restructuring ---
    inner_status = None
    if isinstance(processed_data, dict):
        inner_status = processed_data.get("status")

    # --- 3. Update cumulative approval state ---
    approval_markers = {
        "COMPLIANCE APPROVED": ("compliance_status", "APPROVED"),
        "SIMULATION_ALL_APPROVED": ("simulation_status", "APPROVED"),
        "GROUNDING APPROVED": ("grounding_status", "APPROVED"),
        "JSON APPROVED": ("status", "JSON APPROVED"),
    }

    # Convert feedback to string for scanning approval markers
    feedback_str = (
        json.dumps(processed_data)
        if not isinstance(processed_data, str)
        else processed_data
    )

    matched = [key for key in approval_markers if key in feedback_str]

    if matched:
        approval_path = os.path.join(output_dir, "approval.json")
        approval_state = {}
        if os.path.exists(approval_path):
            try:
                with open(approval_path, "r", encoding="utf-8") as f:
                    approval_state = json.load(f)
            except Exception:
                pass

        for marker in matched:
            key, value = approval_markers[marker]
            approval_state[key] = value

        with open(approval_path, "w", encoding="utf-8") as f:
            json.dump(approval_state, f, indent=2)

    # --- 4. Determine top-level status ---
    status = "REVISION REQUIRED"
    approved_statuses = {
        "JSON APPROVED",
        "COMPLIANCE APPROVED",
        "SIMULATION_ALL_APPROVED",
        "GROUNDING APPROVED",
    }
    if inner_status in approved_statuses:
        status = inner_status

    # --- 5. Fix Double-Nesting & Remove Status from Data ---
    if isinstance(processed_data, dict):
        # If the agent sent {"issues": [...]}, flatten it so 'data' is the list
        if "issues" in processed_data:
            processed_data = processed_data["issues"]
        else:
            # Otherwise, just remove the status key to avoid redundancy
            processed_data = {k: v for k, v in processed_data.items() if k != "status"}

    # --- 6. Build final payload ---
    payload = {
        "status": status,
        "data": processed_data,
    }

    # --- 7. Save to disk ---
    try:
        with open(path, "w", encoding="utf-8") as f:
            logger.debug(f"Loaded iteration feedback: {str(payload)[:400]}")
            json.dump(payload, f, indent=2)
        
        logger.debug(f"Iteration feedback saved with status '{status}'.")
        logger.debug(f"--- [DIAGNOSTIC] Utils: Feedback successfully saved to disk ---")
        return f"SUCCESS: Feedback persisted to {path}"

    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        return f"ERROR: Could not save feedback: {str(e)}"

def _load_template_json(template_path: str) -> Optional[dict]:
    """
    Loads a JSON template from the process_agents/templates directory.
    Returns the parsed JSON as a dict, or None if loading/parsing fails.
    """
    if not os.path.exists(template_path):
        logger.error(f"Template file {template_path} not found.")
        return None

    if os.path.exists(template_path):
        try:
            logger.debug(f"Loading template JSON from {template_path}...")
            with open(template_path, "r", encoding="utf-8") as f:
                template_data = json.load(f)
            # Validate template data before returning
            issues = _validate_process_json(template_data)
            if issues is None or len(issues) > 0:
                logger.error(f"Template file {template_path} is invalid or has issues: {issues}")
                return None
            return template_data
        except Exception as e:
            logger.error(f"Failed to load or parse template file {template_path}: {e}")
            return None
    else:
        logger.error(f"Template file {template_path} does not exist.")
        return None    

def load_process_template() -> Optional[dict]:
    """
    Loads the process template JSON from the templates directory.
    This is used as a fallback if the master process JSON is missing or invalid.
    Returns the template dict if successful, or None if loading/parsing fails.
    """
    template_path = os.path.join(PROJECT_ROOT, "process_agents/templates/", "process_schema.json")
    return _load_template_json(template_path)

# Load the master process JSON from output/process_data.json
def load_master_process_json() -> Union[dict, None]:
    """
    Loads and returns the contents of output/process_data.json as a Python dict.

    Returns:
      - A valid dict if the file exists AND contains a structurally valid process JSON.
      - None if the file is missing, unreadable, empty, locked, or contains validation issues.
    """

    path = os.path.join(PROJECT_ROOT, "output", "process_data.json")
    template_path = os.path.join(PROJECT_ROOT, "process_agents/templates/", "process_schema.json")
    lock_path = os.path.join(PROJECT_ROOT, "output", ".process_data.lock")

    # Wait for lock to clear (writer in progress)
    start = time.time()
    while os.path.exists(lock_path):
        if time.time() - start > 5.0:
            logger.error("Timeout waiting for lock release in load_master_process_json.")
            return None
        time.sleep(0.1)

    # File existence
    if not os.path.exists(path):
        logger.warning(f"{path} does not exist. Attempting to load template file {template_path}.")
        return _load_template_json(template_path)

    try:
        # Read file content
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()

        if not raw:
            logger.error(f"{path} is empty on disk.")
            return None

        # Parse JSON
        try:
            data = json.loads(raw)
        except Exception as e:
            logger.error(f"Failed to parse JSON in {path}: {e}")
            return None

        # Validate using new issue-list validator
        issues = _validate_process_json(data)
        if issues is None:
            logger.error(f"Validation failed for {path}: not a JSON object.")
            return None

        if len(issues) > 0:
            logger.error(f"Validation issues found in {path}: {issues}")
            return None

        return data

    except Exception as e:
        logger.error(f"Unexpected error loading {path}: {e}")
        return None

# Load instruction from a file in the instructions directory
def load_instruction(filename: str) -> str:
    _log_agent_activity(f"Loading instruction from {filename}")
    try:
        instruction_path = os.path.join(PROJECT_ROOT, "instructions", filename)
        with open(instruction_path, "r", encoding="utf-8") as f:
            instruction = f.read()
            logger.debug(f"Instruction content: {instruction[:100]}...")  # Log first 100 chars
            return instruction
    except FileNotFoundError:
        logger.error(f"Instruction file {filename} not found.")
        raise
    except Exception as e:
        logger.error(f"Error loading instruction file {filename}: {e}")
        raise

# Validate that all required instruction files exist and are readable
def validate_instruction_files() -> bool:
    """
    Validates that all instruction files exist and are readable.
    Logs a single consolidated error if any are missing.
    """
    instruction_dir = os.path.join(PROJECT_ROOT, "instructions")

    required_files = [
        "agent.txt",
        "analysis_agent.txt",
        "compliance_agent.txt",
        "consultant_agent.txt",
        "design_agent.txt",
        "doc_generation_agent.txt",
        "edge_inference_agent.txt",
        "json_normalizer_agent.txt",
        "json_review_agent.txt",
        "json_writer_agent.txt",
        "scenario_tester_agent.txt",
        "simulation_agent.txt",
        "subprocess_generator_agent.txt",
        "update_analysis_agent.txt"
    ]

    missing = []
    unreadable = []

    for filename in required_files:
        path = os.path.join(instruction_dir, filename)
        if not os.path.exists(path):
            missing.append(filename)
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                _ = f.read(50)  # sanity check
        except Exception as e:
            unreadable.append((filename, str(e)))

    if missing or unreadable:
        logger.error("Instruction file validation failed.")
        if missing:
            logger.error(f"Missing: {missing}")
        if unreadable:
            logger.error(f"Unreadable: {unreadable}")
        return False
    else:
        _log_agent_activity("All instruction files validated successfully.")
        return True

# ---------------------------------------------------------------------
# Shared cleaner
# ---------------------------------------------------------------------
import re

def _clean_text(text: str) -> str:
    if not text:
        return ""

    # 1. Strip "For context:" prefix from the start of any line
    # (?m) enables multiline mode so ^ matches the start of every line
    text = re.sub(r"(?m)^For context:\s*", "", text)

    # 2. Strip ADK tool traces
    # Remove system metadata lines entirely (called tool / returned result)
    text = re.sub(r"(?m)^\[.*?\]\s*called tool `.*?` with parameters:.*\n?", "", text)
    text = re.sub(r"(?m)^\[.*?\]\s*`.*?` tool returned result:.*\n?", "", text)
    
    # Remove only the prefix for "said:" to keep the actual message content
    text = re.sub(r"(?m)^\[.*?\]\s*said:\s*", "", text)

    # 3. Strip markdown fences
    # Remove opening fences (e.g., ```json) and closing fences
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("```", "")

    return text.strip()

def _safe_clean(text: str) -> str:
    cleaned = _clean_text(text)
    return cleaned if cleaned.strip() else "<no-op>"

STATUS_MARKERS = [
    "JSON APPROVED",
    "REVISION REQUIRED",
    "COMPLIANCE APPROVED",
    "SIMULATION_ALL_APPROVED",
    "GROUNDING APPROVED"
]

def _is_status_marker(text: str) -> bool:
    return any(marker in text for marker in STATUS_MARKERS)


# ---------------------------------------------------------------------
# BEFORE MODEL: scrub messages text (for logs / downstream agents)
# ---------------------------------------------------------------------

def review_messages(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    # Collect available context attributes and log them in a single debug call
    attrs = []
    for attr in ["agent_name", "agent_id", "pipeline_name", "stage_name", "metadata", "tool_name", "error_code", "error_message"]:
        val = getattr(callback_context, attr, None)
        if val:
            attrs.append(f"{attr.upper()}: {val}")
    if attrs:
        error_code = getattr(callback_context, "error_code", None)
        error_message = getattr(callback_context, "error_message", None)
        logger.debug(f"--- [DIAGNOSTIC] Utils: Reviewing messages with context | {' | '.join(attrs)} ---")

    if not llm_request or not getattr(llm_request, "contents", None):
        return None

    for content in llm_request.contents:
        if not hasattr(content, "parts"):
            continue

        for part in content.parts:
            # Only touch pure text parts
            if hasattr(part, "text") and isinstance(part.text, str):
                # Do NOT touch status markers
                if _is_status_marker(part.text):
                    continue
                # Light clean only – no <no-op>, no dropping
                cleaned = _clean_text(part.text)
                part.text = cleaned if cleaned else part.text

    return None

# ---------------------------------------------------------------------
# AFTER MODEL: scrub outgoing text (for logs / downstream agents)
# ---------------------------------------------------------------------
def review_outputs(callback_context: CallbackContext, llm_response: LlmResponse) -> Optional[LlmResponse]:
    # Collect available context attributes and log them in a single debug call
    attrs = []
    for attr in ["agent_name", "agent_id", "pipeline_name", "stage_name", "metadata", "tool_name", "error_code", "error_message"]:
        val = getattr(callback_context, attr, None)
        if val:
            attrs.append(f"{attr.upper()}: {val}")
    if attrs and llm_response:
        error_code = getattr(llm_response, "error_code", None)
        error_message = getattr(llm_response, "error_message", None)
        logger.debug(f"--- [DIAGNOSTIC] Utils: Reviewing outputs with context | {' | '.join(attrs)} {llm_response} ---")

    if not llm_response or not getattr(llm_response, "candidates", None):
        return llm_response

    for candidate in llm_response.candidates:
        content = getattr(candidate, "content", None)
        if not content or not hasattr(content, "parts"):
            continue

        for part in content.parts:
            if (
                hasattr(part, "text")
                and isinstance(part.text, str)
                and len(part.__dict__.keys()) == 1
            ):
                if _is_status_marker(part.text):
                    continue
                cleaned = _clean_text(part.text)
                if cleaned:
                    part.text = cleaned

    return llm_response

class CleanedStdout:
    def __init__(self, path: str):
        self.file = open(path, "w", encoding="utf-8")

    def write(self, text):
        try:
            # Convert bytes → str safely
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")

            from .utils import _clean_text, _is_status_marker

            # Preserve status markers exactly
            if _is_status_marker(text):
                self.file.write(text)
                return

            cleaned = _clean_text(text)
            self.file.write(cleaned)

        except Exception:
            # Fallback: write raw text (converted to str if needed)
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            self.file.write(text)

    def flush(self):
        self.file.flush()
