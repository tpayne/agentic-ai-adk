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
        "application gateway": "mxgraph.azure.network.application_gateway",
        "application gateways": "mxgraph.azure.network.application_gateways",
        "application gateway containers": "mxgraph.azure.network.application_gateway_containers",
        "azure firewall manager": "mxgraph.azure.networking.azure_firewall_manager",
        "azure firewall policy": "mxgraph.azure.networking.azure_firewall_policy",
        "bastion": "mxgraph.azure.networking.bastions",
        "bastions": "mxgraph.azure.networking.bastions",
        "dns private resolver": "mxgraph.azure.networking.dns_private_resolver",
        "dns security policy": "mxgraph.azure.networking.dns_security_policy",
        "dns zones": "mxgraph.azure.networking.dns_zones",
        "expressroute circuits": "mxgraph.azure.networking.expressroute_circuits",
        "firewalls": "mxgraph.azure.networking.firewalls",
        "front door": "mxgraph.azure.networking.front_doors",
        "front doors": "mxgraph.azure.networking.front_doors",
        "ip address manager": "mxgraph.azure.networking.ip_address_manager",
        "private link hub": "mxgraph.azure.networking.private_link_hub",
        "service endpoint policies": "mxgraph.azure.networking.service_endpoint_policies",
        "virtual wan hub": "mxgraph.azure.networking.virtual_wan_hub",
        "virtual wans": "mxgraph.azure.networking.virtual_wans",
        "vpn gateway": "mxgraph.azure.network.vpn_gateway",

        # Compute
        "availability sets": "mxgraph.azure.compute.availability_sets",
        "batch accounts": "mxgraph.azure.compute.batch_accounts",
        "container instances": "mxgraph.azure.compute.container_instances",
        "container services": "mxgraph.azure.compute.container_services",
        "disk encryption sets": "mxgraph.azure.compute.disk_encryption_sets",
        "disks": "mxgraph.azure.compute.disks",
        "image templates": "mxgraph.azure.compute.image_templates",
        "images": "mxgraph.azure.compute.images",
        "kubernetes services": "mxgraph.azure.compute.kubernetes_services",
        "virtual machine": "mxgraph.azure.compute.vm",
        "virtual machines": "mxgraph.azure.compute.vm",
        "vm ": "mxgraph.azure.compute.vm",
        " vm": "mxgraph.azure.compute.vm",
        "vm scale sets": "mxgraph.azure.compute.vm_scale_sets",

        # Storage / Data
        "adls gen1": "mxgraph.azure.storage.data_lake_storage",
        "adls gen2": "mxgraph.azure.storage.data_lake_storage",  # corrected to Gen1 image
        "data lake": "mxgraph.azure.storage.data_lake_storage",
        "data lake storage": "mxgraph.azure.storage.data_lake_storage",
        "data lake store gen1": "mxgraph.azure.storage.data_lake_storage",
        "data lake storage gen1": "mxgraph.azure.storage.data_lake_storage",
        "data lake store gen2": "mxgraph.azure.storage.data_lake_storage",
        "data lake storage gen2": "mxgraph.azure.storage.data_lake_storage",
        "sql database": "mxgraph.azure.databases.sql_database",
        "sql server": "mxgraph.azure.databases.sql_server",
        "sql stretch database": "mxgraph.azure.databases.azure_sql_server_stretch_databases",
        "sql vm": "mxgraph.azure.databases.azure_sql_vm",
        "sql managed instance": "mxgraph.azure.databases.sql_managed_instance",
        "sql elastic pools": "mxgraph.azure.databases.sql_elastic_pools",
        "instance pools": "mxgraph.azure.databases.instance_pools",
        "oracle database": "mxgraph.azure.databases.oracle_database",
        "azure data explorer clusters": "mxgraph.azure.databases.azure_data_explorer_clusters",

        # AI / ML
        "ai studio": "mxgraph.azure.ai_machine_learning.ai_studio",
        "anomaly detector": "mxgraph.azure.ai_machine_learning.anomaly_detector",
        "applied ai": "mxgraph.azure.ai_machine_learning.azure_applied_ai",
        "batch ai": "mxgraph.azure.ai_machine_learning.batch_ai",
        "bonsai": "mxgraph.azure.ai_machine_learning.bonsai",
        "bot services": "mxgraph.azure.ai_machine_learning.bot_services",
        "cognitive services": "mxgraph.azure.ai_machine_learning.cognitive_services",
        "computer vision": "mxgraph.azure.ai_machine_learning.computer_vision",
        "content moderators": "mxgraph.azure.ai_machine_learning.content_moderators",
        "content safety": "mxgraph.azure.ai_machine_learning.content_safety",
        "language understanding": "mxgraph.azure.ai_machine_learning.language_understanding",
        "azure openai": "mxgraph.azure.ai_machine_learning.azure_openai",
        "machine learning studio workspaces": "mxgraph.azure.ai_machine_learning.machine_learning_studio_workspaces",
        "speech services": "mxgraph.azure.ai_machine_learning.speech_services",
        "translator text": "mxgraph.azure.ai_machine_learning.translator_text",

        # Analytics
        "analysis services": "mxgraph.azure.analytics.analysis_services",
        "azure databricks": "mxgraph.azure.analytics.azure_databricks",
        "data factory": "mxgraph.azure.analytics.data_factory",
        "data lake analytics": "mxgraph.azure.analytics.data_lake_analytics",
        "endpoint analytics": "mxgraph.azure.analytics.endpoint_analytics",
        "event hub clusters": "mxgraph.azure.analytics.event_hub_clusters",
        "event hubs": "mxgraph.azure.analytics.event_hubs",
        "log analytics workspaces": "mxgraph.azure.analytics.log_analytics_workspaces",
        "stream analytics jobs": "mxgraph.azure.analytics.stream_analytics_jobs",
        "synapse analytics": "mxgraph.azure.analytics.azure_synapse_analytics",
        "azure workbooks": "mxgraph.azure.analytics.azure_workbooks",

        # App Services
        "api management services": "mxgraph.azure.app_services.api_management_services",
        "app service certificates": "mxgraph.azure.app_services.app_service_certificates",
        "app service domains": "mxgraph.azure.app_services.app_service_domains",
        "app service environments": "mxgraph.azure.app_services.app_service_environments",
        "app service plans": "mxgraph.azure.app_services.app_service_plans",
        "app services": "mxgraph.azure.app_services.app_services",
        "cdn profiles": "mxgraph.azure.app_services.cdn_profiles",
        "notification hubs": "mxgraph.azure.app_services.notification_hubs",
        "search services": "mxgraph.azure.app_services.search_services",

        # Security / Identity
        "active directory": "mxgraph.azure.identity.active_directory",
        "entra id": "mxgraph.azure.identity.active_directory",
        "entra connect": "mxgraph.azure.identity.entra_connect",
        "entra domain services": "mxgraph.azure.identity.entra_domain_services",
        "entra global secure access": "mxgraph.azure.identity.entra_global_secure_access",
        "entra id protection": "mxgraph.azure.identity.entra_id_protection",
        "entra internet access": "mxgraph.azure.identity.entra_internet_access",
        "entra managed identities": "mxgraph.azure.identity.entra_managed_identities",
        "entra private access": "mxgraph.azure.identity.entra_private_access",
        "entra pim": "mxgraph.azure.identity.entra_privileged_identity_management",
        "entra verified id": "mxgraph.azure.identity.entra_verified_id",
        "entra identity": "mxgraph.azure.identity.entra_identity",
        "active directory connect health": "mxgraph.azure.identity.active_directory_connect_health",
        "azure defender": "mxgraph.azure.security.azure_defender",
        "defender": "mxgraph.azure.security.defender",
        "defender easm": "mxgraph.azure.security.ms_defender_easm",
        "dependency monitor": "mxgraph.azure.security.dependency_monitor",
        "key vault": "mxgraph.azure.security.key_vaults",
        "tenant key": "mxgraph.azure.security.tenant_key",
        "key": "mxgraph.azure.security.key",

        # Governance / Monitoring
        "activity log": "mxgraph.azure.management.activity_log",
        "diagnostic settings": "mxgraph.azure.management.diagnostics_settings",
        "metrics": "mxgraph.azure.management.metrics",
        "monitor": "mxgraph.azure.management.monitor",
        "network watcher": "mxgraph.azure.management.network_watcher",
        "sap azure monitor": "mxgraph.azure.management.sap_azure_monitor",
        "scale": "mxgraph.azure.management.scale",
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

        # Identity
        "authentication entra id": "mxgraph.citrix2.authentication_ms_entra_id",
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
        "monitor": "mxgraph.gcp2.stackdriver",
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
        "auto scaling group": "mxgraph.aws4.group_auto_scaling_group",
        "cluster": "mxgraph.veeam.cluster",
        "dr site": "mxgraph.veeam.dr_site",
        "hyper-v host": "mxgraph.veeam.hyper_v_host",
        "server stack": "mxgraph.veeam.server_stack",
        "virtual network": "img/lib/azure2/networking/Virtual_Network.svg",
        "vnet": "img/lib/azure2/networking/Virtual_Network.svg",
        "subnet": "img/lib/azure2/networking/Subnet.svg",
        "resource group": "img/lib/azure2/general/Resource_Groups.svg",
        "management group": "img/lib/azure2/general/Management_Groups.svg",
        "region": "img/lib/azure2/general/Region.svg",
        "availability zone": "img/lib/azure2/general/Availability_Zones.svg",
        "landing zone": "img/lib/azure2/general/Region.svg",
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
        "azure defender": "img/lib/azure2/security/Azure_Defender.svg",
        "defender": "img/lib/azure2/security/Azure_Defender.svg",
    }

    AWS_CONTAINERS = {
        "vpc": "img/lib/aws4/networking_content/Virtual-private-cloud.svg",
        "subnet": "img/lib/aws4/networking_content/Subnet.svg",
        "region": "img/lib/aws4/general/Region.svg",
        "availability zone": "img/lib/aws4/general/Availability-zone.svg",
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
        Repairs malformed <Array points="x y x y"> tags into valid Draw.io format.
        """
        import re

        def convert(match):
            pts = match.group(1).strip().split()
            mxpts = []
            for i in range(0, len(pts), 2):
                try:
                    x = pts[i]
                    y = pts[i+1]
                    mxpts.append(f'<mxPoint x="{x}" y="{y}" />')
                except IndexError:
                    continue
            return '<Array as="points">' + "".join(mxpts) + '</Array>'

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

        for cell in root.findall(".//mxCell"):
            if cell.get("vertex") != "1":
                continue

            value = (cell.get("value") or "").lower()
            if not value:
                continue

            style = cell.get("style", "") or ""

            # 1) Container mapping (VNet, Subnet, Region, etc.) – image-based
            matched_container = None
            for key, img_path in container_map.items():
                if key in value:
                    matched_container = img_path
                    break

            if matched_container:
                # Overwrite style to be an image-based, stretchable container
                # Keep some layout-related flags if present (rounded, dashed, etc.)
                base_flags = []
                if "rounded=1" in style:
                    base_flags.append("rounded=1")
                if "dashed=1" in style:
                    base_flags.append("dashed=1")
                if "whiteSpace=wrap" in style:
                    base_flags.append("whiteSpace=wrap")
                if "html=1" in style or not base_flags:
                    base_flags.append("html=1")

                style_parts = [
                    "shape=image",
                    f"image={matched_container}",
                    "aspect=fixed",
                ] + base_flags

                cell.set("style", ";".join(style_parts) + ";")
                # Once treated as container, we don't also treat it as a service icon
                continue

            # 2) Service icon mapping (mxgraph.*) – only if not already platform-specific
            if "shape=mxgraph." in style:
                continue

            matched_shape = None
            for key, shape in shape_map.items():
                if key in value:
                    matched_shape = shape
                    break

            if not matched_shape:
                continue

            if style and not style.endswith(";"):
                style += ";"
            style = f"shape={matched_shape};" + style
            cell.set("style", style)

        try:
            return ET.tostring(root, encoding="unicode")
        except Exception as e:
            logger.error(f"Failed to serialize XML after shape mapping: {e}")
            return raw_xml

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
            ET.fromstring(raw_xml)
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
