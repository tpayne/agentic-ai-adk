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
        "vpc": "mxgraph.aws3.vpc",
        "vpc nat gateway": "mxgraph.aws3.vpc_nat_gateway",
        "vpc peering": "mxgraph.aws3.vpc_peering",
        "elastic network interface": "mxgraph.aws4.elastic_network_interface",
        "elastic network adapter": "mxgraph.aws4.elastic_network_adapter",
        "network acl": "mxgraph.aws4.network_access_control_list",
        "cloud wan virtual pop": "mxgraph.aws4.cloud_wan_virtual_pop",

        # Compute
        "emr cluster": "mxgraph.aws3.emr_cluster",
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
        "activity log": "mxgraph.gcp2.stackdriver",
        "cloud logging": "mxgraph.gcp2.cloud_logging",
        "diagnostic settings": "mxgraph.gcp2.stackdriver",
        "operations suite": "mxgraph.gcp2.stackdriver",
        "stackdriver": "mxgraph.gcp2.stackdriver",
        "cloud trace": "mxgraph.gcp2.stackdriver",
        "cloud profiler": "mxgraph.gcp2.stackdriver",
        "error reporting": "mxgraph.gcp2.stackdriver",
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
        "vpc network": "img/lib/gcp2/networking/VPC-Network.svg",
        "vpc ": "img/lib/gcp2/networking/VPC-Network.svg",
        "subnet": "img/lib/gcp2/networking/Subnet.svg",
        "region": "img/lib/gcp2/general/Region.svg",
        "zone": "img/lib/gcp2/general/Zone.svg",
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

    def _style_for_shape_ref(ref: str) -> str:
        """
        Real draw.io icon sets are NOT all addressed the same way. Verified
        directly against draw.io's own shipped assets (github.com/jgraph/drawio)
        and real-world exports:

          - Modern Azure icon set: image-only, no vector stencil namespace.
            (ref ending in .svg / starting with img/ -> rendered as an image.)
          - Modern AWS4 *individual service* icons: NOT directly renderable
            via a bare shape=mxgraph.aws4.<name> reference. They must be
            wrapped in the resourceIcon carrier shape, e.g. AWS Lambda is
            shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;
            -- a bare shape=mxgraph.aws4.lambda is not a registered stencil
            on its own. (AWS4 *group/container* shapes, e.g.
            mxgraph.aws4.group, are the one exception and ARE used bare.)
          - GCP2 and legacy AWS3: directly renderable via a bare shape=
            reference (confirmed working real-world usage).
        """
        if ref.endswith(".svg") or ref.startswith("img/"):
            return f"image;aspect=fixed;html=1;image={ref};"
        if ref.startswith("mxgraph.aws4.") and not ref.startswith("mxgraph.aws4.group"):
            return (
                "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
                "fillColor=#ED7100;strokeColor=#ffffff;dashed=0;"
                "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
                f"fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon={ref};"
            )
        return f"shape={ref};"

    _AWS4_BARE_ICON_RE = re.compile(r'shape=mxgraph\.aws4\.(?!resourceIcon|productIcon|group)([a-zA-Z0-9_]+);?')

    def _repair_bare_aws4_icons(style: str) -> str:
        """
        Same idea as _repair_legacy_azure_shapes: LLM-authored XML sometimes
        hardcodes a bare shape=mxgraph.aws4.<name> directly, bypassing our
        AWS_SHAPES dictionary entirely. Since that form isn't a registered
        stencil for individual AWS4 service icons, repair it in place using
        the same resourceIcon wrapper.
        """
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
            #    (either a vector stencil, or an already-set azure2 image ref).
            if "shape=mxgraph." in style or "image=img/lib/" in style:
                continue

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
