# process_agents/cloudarch_finops_agent.py
#
# CloudArch analogue of cloudarch_simulation_agent.py, but for cost rather
# than resilience/scalability/latency: estimates a rough monthly cost per
# component (and an architecture-wide total) from the diagram's own
# shape/label/bullet text, and generates pattern-based cost-optimization
# recommendations. Same "grounded in the diagram itself, not a fabricated
# numeric field" philosophy -- there is no dedicated cost/instance-size
# schema anywhere in this project (confirmed: save_drawio_structured's own
# component shape is {id, zone_id, label, bullets, shape, icon_color,
# color, width} -- no cost/size field), so sizing signals are recovered
# from each vertex's shape_slug (service family) plus whatever free text
# the generating agent wrote into that component's bullets.
#
# Catalog prices ground any resource with an explicit SKU and all monthly
# billable usage meters. Components without exact matching catalog rates
# retain the existing order-of-magnitude heuristic estimates.

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from google.genai import types

from ..common.utils import load_drawio, load_master_process_json, load_requirements_summary, parse_drawio_graph
from .pricing import lookup_catalog_resource_price

logger = logging.getLogger("ProcessArchitect.CloudArchFinOps")

CLOUDARCH_FINOPS_RESULTS_PATH = "output/cloudarch_finops_results.json"

# Exact shape_slug -> monthly USD. Covers the service families most likely
# to come from this project's own CloudArch_Agent (which picks real
# AWS4/Azure/GCP2 drawio stencil names, optionally via a search_shapes
# tool -- see instructions/cloudarch/cloudarch_agent.txt -- so there is no
# fixed, closed vocabulary to key against). Anything not listed here falls
# through to the category-keyword fallback below rather than going
# unestimated.
_DIRECT_PRICING_USD_PER_MONTH: Dict[str, float] = {
    # AWS
    "ec2": 70.0, "lambda": 5.0, "rds": 120.0, "dynamodb": 25.0, "s3": 25.0,
    "ebs": 20.0, "elastic_load_balancing_elb": 20.0, "elb": 20.0, "alb": 20.0,
    "cloudfront": 10.0, "elasticache": 50.0, "sqs": 10.0, "sns": 5.0,
    "eks": 75.0, "ecs": 75.0, "fargate": 40.0, "api_gateway": 10.0,
    "nat_gateway": 35.0, "route_53": 1.0, "kms": 1.0, "secrets_manager": 2.0,
    "cloudwatch": 10.0, "kinesis": 25.0,
    # Azure
    "virtual_machines": 70.0, "sql_database": 120.0, "storage_accounts": 25.0,
    "managed_disks": 20.0, "load_balancer": 20.0, "application_gateway": 25.0,
    "cdn": 10.0, "cache_for_redis": 50.0, "service_bus": 10.0,
    "functions": 5.0, "aks": 75.0, "container_apps": 40.0, "api_management": 10.0,
    "key_vault": 1.0, "monitor": 10.0, "event_hubs": 25.0,
    # GCP
    "compute_engine": 70.0, "cloud_run": 5.0, "cloud_sql": 120.0,
    "cloud_storage": 25.0, "persistent_disk": 20.0, "cloud_load_balancing": 20.0,
    "cloud_cdn": 10.0, "memorystore": 50.0, "pub_sub": 10.0,
    "cloud_functions": 5.0, "kubernetes_engine": 75.0, "cloud_run_jobs": 5.0,
    "apigee": 10.0, "cloud_kms": 1.0, "cloud_logging": 10.0, "firestore": 25.0,
    "bigtable": 120.0, "bigquery": 30.0,
}

# Open-vocabulary fallback: keyword -> category, checked against the
# component's shape_slug + label + bullet text combined (so e.g. a
# non-catalogued slug like "aws4.aurora_instance" still resolves via the
# "aurora" keyword even though it has no _DIRECT_PRICING_USD_PER_MONTH
# entry of its own).
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    # Deliberately NOT a bare "instance" -- that's too generic a substring
    # (confirmed directly: it wrongly classified "aurora_instance" as
    # compute instead of database, since "instance" is common across
    # many managed-service names, not just VMs).
    "compute": ["ec2", "vm", "virtual_machine", "compute_engine", "droplet", "vmss"],
    "serverless": [
        "lambda", "function", "cloud_run", "app_service", "container_apps",
        "serverless", "app_engine", "elastic_beanstalk",
    ],
    "container_orchestration": ["eks", "aks", "gke", "kubernetes", "ecs", "fargate", "container_registry"],
    "database": [
        "rds", "sql", "database", "dynamodb", "cosmos", "firestore", "bigtable",
        "aurora", "mysql", "postgres", "mariadb", "cloud_sql",
    ],
    "cache": ["redis", "elasticache", "memorystore", "memcached", "cache"],
    "storage": ["s3", "blob", "storage_account", "cloud_storage", "bucket", "object_storage"],
    "block_storage": ["ebs", "disk", "persistent_disk", "managed_disk"],
    "queue_messaging": [
        "sqs", "sns", "pub_sub", "pubsub", "service_bus", "eventbridge",
        "kafka", "kinesis", "event_hub", "queue", "topic",
    ],
    "network_lb": ["elb", "alb", "load_balancer", "application_gateway", "cloud_load_balancing", "nlb"],
    "cdn": ["cloudfront", "cdn"],
    "dns_networking": [
        "route_53", "route53", "vpc", "vnet", "dns", "nat_gateway", "vpn",
        "peering", "transit_gateway", "expressroute", "interconnect",
    ],
    "monitoring_logging": ["cloudwatch", "monitor", "stackdriver", "cloud_logging", "cloud_trace", "application_insights"],
    "identity_security": [
        "iam", "kms", "key_vault", "secrets_manager", "cloud_kms", "waf",
        "guardduty", "security_center", "cloud_armor",
    ],
    "api_gateway": ["api_gateway", "apim", "apigee", "api_management"],
}

_CATEGORY_DEFAULT_USD_PER_MONTH: Dict[str, float] = {
    "compute": 70.0, "serverless": 5.0, "container_orchestration": 75.0,
    "database": 120.0, "cache": 50.0, "storage": 25.0, "block_storage": 20.0,
    "queue_messaging": 10.0, "network_lb": 20.0, "cdn": 10.0,
    "dns_networking": 15.0, "monitoring_logging": 10.0,
    "identity_security": 2.0, "api_gateway": 10.0,
}

# Keyword -> cost multiplier, checked against the same combined haystack.
# First match wins (checked in this order -- biggest tiers first so e.g.
# "2xlarge" doesn't also trip the plain "large" rule it happens to contain
# as a substring).
_SIZE_MULTIPLIER_KEYWORDS: List[Tuple[Tuple[str, ...], float]] = [
    (("2xlarge", "4xlarge", "8xlarge", "16xlarge", "metal"), 4.0),
    (("xlarge", "high-performance", "high performance", "dedicated", "premium"), 2.0),
    (("large",), 1.5),
    (("nano", "micro", "small", "free tier", "free_tier"), 0.4),
]

_AUTOSCALING_KEYWORDS = ("auto scal", "autoscal", "auto-scal", "elastic")
_RESERVED_CAPACITY_KEYWORDS = ("reserved", "savings plan", "committed use", "committed-use", "reservation")
_LIFECYCLE_KEYWORDS = (
    "lifecycle", "tiering", "tiered", "glacier", "archive", "cold",
    "nearline", "coldline", "infrequent access",
)
_ALWAYS_ON_CATEGORIES = {"compute", "container_orchestration", "database", "cache"}


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _split_label_and_bullets(value: str) -> Tuple[str, List[str]]:
    """A vertex's raw `value` is `<b>Label</b><br/><font ...>bullet</font>...`
    (see cloudarch_layout_agent.py's own _html_value) -- splits it back into
    a clean label and a list of clean bullet strings."""
    parts = (value or "").split("<br/>")
    label = _strip_html(parts[0]) if parts else ""
    bullets = [_strip_html(p) for p in parts[1:] if _strip_html(p)]
    return label, bullets


def _classify_component(shape_slug: str, haystack: str) -> Tuple[Optional[str], float, str]:
    """Returns (category_or_None, monthly_cost_usd, confidence). category is
    populated whenever EITHER the exact-slug table OR the keyword fallback
    matched (used by the recommendation rules below, e.g. "is this an
    always-on compute-ish resource") -- confidence separately records
    WHICH one actually set the cost number."""
    slug_lower = (shape_slug or "").lower()

    category = None
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            category = cat
            break

    if slug_lower in _DIRECT_PRICING_USD_PER_MONTH:
        return category, _DIRECT_PRICING_USD_PER_MONTH[slug_lower], "direct"
    if category:
        return category, _CATEGORY_DEFAULT_USD_PER_MONTH[category], "category"
    return None, 0.0, "unclassified"


def _size_multiplier(haystack: str) -> float:
    for keywords, multiplier in _SIZE_MULTIPLIER_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return multiplier
    return 1.0


def _generate_optimization_recommendations(
    components: List[Dict[str, Any]], touched_ids: Set[str], full_text_lower: str
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []

    oversized = [c for c in components if c["size_multiplier"] >= 2.0]
    if oversized:
        recommendations.append({
            "title": "Verify large/high-tier instance sizing against real load",
            "detail": (
                "The following component(s) are labeled with a large or high-performance sizing tier: "
                + ", ".join(c["label"] for c in oversized)
                + ". Large instance tiers are a common source of overspend when sized by guess rather "
                "than observed utilization -- right-size against real metrics before committing budget."
            ),
            "components_involved": [c["label"] for c in oversized],
        })

    always_on = [c for c in components if c["category"] in _ALWAYS_ON_CATEGORIES]
    no_autoscaling = [c for c in always_on if not any(kw in c["haystack"] for kw in _AUTOSCALING_KEYWORDS)]
    if no_autoscaling:
        recommendations.append({
            "title": "No autoscaling noted for always-on resources",
            "detail": (
                "No autoscaling/elastic-capacity policy is mentioned for: "
                + ", ".join(c["label"] for c in no_autoscaling)
                + ". Paying for fixed capacity around the clock, rather than scaling with real demand, is "
                "one of the most common sources of avoidable cloud spend -- consider an autoscaling policy "
                "or a serverless alternative."
            ),
            "components_involved": [c["label"] for c in no_autoscaling],
        })

    if always_on and not any(kw in full_text_lower for kw in _RESERVED_CAPACITY_KEYWORDS):
        recommendations.append({
            "title": "No reserved-capacity/savings-plan commitment mentioned",
            "detail": (
                "None of this diagram's always-on compute/database/cache resources mention a reserved "
                "instance, savings plan, or committed-use discount. For steady-state workloads these "
                "commitments commonly cut compute/database costs 30-60% versus on-demand pricing -- worth "
                "evaluating once real usage patterns are established."
            ),
            "components_involved": [c["label"] for c in always_on],
        })

    storage_components = [c for c in components if c["category"] in ("storage", "block_storage")]
    no_lifecycle = [c for c in storage_components if not any(kw in c["haystack"] for kw in _LIFECYCLE_KEYWORDS)]
    if no_lifecycle:
        recommendations.append({
            "title": "No storage lifecycle/tiering policy mentioned",
            "detail": (
                "No lifecycle or tiering policy is mentioned for: " + ", ".join(c["label"] for c in no_lifecycle)
                + ". Moving colder data to a cheaper storage tier (e.g. S3 Infrequent Access/Glacier, Azure "
                "Cool/Archive, GCP Nearline/Coldline) is often a low-effort, ongoing saving."
            ),
            "components_involved": [c["label"] for c in no_lifecycle],
        })

    orphaned = [c for c in components if c["id"] not in touched_ids]
    if orphaned:
        recommendations.append({
            "title": "Component(s) with no connections in this diagram",
            "detail": (
                ", ".join(c["label"] for c in orphaned)
                + " have no edges in or out of them in this diagram. If genuinely unused, decommissioning "
                "removes their cost entirely; if this is just a missing connection, verify the diagram is "
                "complete."
            ),
            "components_involved": [c["label"] for c in orphaned],
        })

    return recommendations


def _persist_cloudarch_finops_results(results: Dict[str, Any]) -> None:
    try:
        import os
        os.makedirs("output", exist_ok=True)
        with open(CLOUDARCH_FINOPS_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.debug(f"CloudArch FinOps results saved to {CLOUDARCH_FINOPS_RESULTS_PATH}")
    except Exception:
        logger.exception("Failed to persist CloudArch FinOps results.")


def estimate_cloudarch_finops(xml_content: Optional[str] = None) -> str:
    """
    Estimates monthly costs and optimization opportunities from diagram
    components. Provider catalog prices are used for any resource with an
    explicit SKU and monthly usage meters when every meter has a unique
    matching rate. Otherwise, the existing category heuristic is retained.
    """
    try:
        if not xml_content:
            loaded = load_drawio()
            if loaded.get("status") != "OK" or not loaded.get("xml"):
                return json.dumps({
                    "error": "no_diagram_available",
                    "detail": "No cloud architecture diagram has been saved yet.",
                })
            xml_content = loaded["xml"]

        graph = parse_drawio_graph(xml_content)
        vertices, edges = graph["vertices"], graph["edges"]
        if not vertices:
            return json.dumps({
                "error": "no_cost_data_available",
                "detail": "The diagram has no recognizable cloud-service icons to estimate cost for.",
            })

        touched_ids: Set[str] = set()
        for e in edges:
            if e.get("source"):
                touched_ids.add(e["source"])
            if e.get("target"):
                touched_ids.add(e["target"])

        components: List[Dict[str, Any]] = []
        full_text_parts: List[str] = []
        pricing_cache: Dict[Tuple[str, ...], Optional[Dict[str, Any]]] = {}
        for v in vertices:
            label, bullets = _split_label_and_bullets(v.get("value", ""))
            haystack = f"{(v.get('shape_slug') or '').lower()} {label.lower()} {' '.join(bullets).lower()}"
            full_text_parts.append(haystack)

            category, base_cost, confidence = _classify_component(v.get("shape_slug", ""), haystack)
            multiplier = _size_multiplier(haystack)
            pricing_diagnostic: Dict[str, str] = {}
            live_price = lookup_catalog_resource_price(
                v.get("shape_provider", ""),
                v.get("shape_slug", ""),
                haystack,
                pricing_cache,
                pricing_diagnostic,
            )

            components.append({
                "id": v["id"],
                "label": label or v.get("value", v["id"]),
                "shape_slug": v.get("shape_slug", ""),
                "category": category,
                "confidence": confidence,
                "size_multiplier": multiplier,
                "monthly_cost_usd": (
                    live_price["monthly_cost_usd"]
                    if live_price is not None
                    else round(base_cost * multiplier, 2)
                ),
                "pricing_basis": (
                    live_price.get("pricing_basis", "provider_catalog")
                    if live_price is not None else "heuristic"
                ),
                "pricing_source": live_price["source"] if live_price is not None else None,
                "pricing_sku": live_price["sku"] if live_price is not None else None,
                "pricing_region": live_price["region"] if live_price is not None else None,
                "pricing_usage_meters": live_price["usage_meters"] if live_price is not None else None,
                "pricing_assumption": live_price["assumption"] if live_price is not None else None,
                "pricing_fallback_reason": (
                    pricing_diagnostic.get("reason") or None if live_price is None else None
                ),
                "haystack": haystack,  # internal only -- stripped before returning below
            })

        full_text_lower = " ".join(full_text_parts)
        total_cost = round(sum(c["monthly_cost_usd"] for c in components), 2)
        unclassified = [c for c in components if c["confidence"] == "unclassified"]

        recommendations = _generate_optimization_recommendations(components, touched_ids, full_text_lower)

        unclassified_fraction = len(unclassified) / max(1, len(components))
        cost_risk_rating = "Low"
        if len(recommendations) >= 3 or unclassified_fraction > 0.4:
            cost_risk_rating = "High"
        elif len(recommendations) >= 1 or unclassified_fraction > 0.15:
            cost_risk_rating = "Medium"

        public_components = [{k: v for k, v in c.items() if k != "haystack"} for c in components]
        provider_priced_components = [
            c for c in components if c["pricing_basis"].startswith("provider_catalog")
        ]
        heuristic_component_count = len(components) - len(provider_priced_components)
        pricing_sources = sorted({c["pricing_source"] for c in provider_priced_components})
        fallback_reasons: Dict[str, List[str]] = {}
        for component in components:
            reason = component.get("pricing_fallback_reason")
            if reason:
                fallback_reasons.setdefault(reason, []).append(component["label"])
        pricing_fallback_reasons = [
            {"components": labels, "reason": reason}
            for reason, labels in fallback_reasons.items()
        ]
        if provider_priced_components:
            pricing_method_summary = (
                f"{len(provider_priced_components)} of {len(components)} component costs are grounded "
                f"in provider pricing catalogs ({', '.join(pricing_sources)}), using explicit details "
                "where available and representative baseline usage assumptions otherwise."
            )
            if heuristic_component_count:
                pricing_method_summary += (
                    f" {heuristic_component_count} use heuristic estimates; "
                    + " ".join(
                        f"{', '.join(item['components'])}: {item['reason']}"
                        for item in pricing_fallback_reasons
                    )
                )
        else:
            pricing_method_summary = (
                f"No component costs were grounded in provider pricing catalogs; all {len(components)} "
                "component costs use heuristic estimates."
            )
            if pricing_fallback_reasons:
                pricing_method_summary += " " + " ".join(
                    f"{', '.join(item['components'])}: {item['reason']}"
                    for item in pricing_fallback_reasons
                )

        result = {
            "cost_estimate": {
                "total_monthly_cost_usd": total_cost,
                "currency": "USD",
                "components": public_components,
                "unclassified_component_count": len(unclassified),
                "provider_priced_component_count": len(provider_priced_components),
                "heuristic_component_count": heuristic_component_count,
                "pricing_sources": pricing_sources,
                "pricing_method_summary": pricing_method_summary,
                "pricing_fallback_reasons": pricing_fallback_reasons,
            },
            "optimization_recommendations": recommendations,
            "cost_risk_rating": cost_risk_rating,
            "component_count": len(components),
        }
        _persist_cloudarch_finops_results(result)
        return json.dumps(result)

    except Exception as e:
        logger.exception("CloudArch FinOps estimation failed.")
        return json.dumps({
            "error": "cloudarch_finops_estimation_failed",
            "detail": str(e),
        })


# ============================================================
# LLM AGENT: CLOUDARCH FINOPS QUERY AGENT (ON-DEMAND, USER-FACING)
# ============================================================
# On-demand only, same reasoning as cloudarch_simulation_query_agent --
# NOT wired as a pipeline-internal auto-revision gate.
from ..common.agent_wrappers import ProcessLlmAgent

cloudarch_finops_query_agent = ProcessLlmAgent(
    name="CloudArch_FinOps_Agent",
    description=(
        "Estimates the monthly cost of an EXISTING cloud architecture diagram, per component and in "
        "total, grounds explicitly detailed resources in public provider catalogs when possible, "
        "and recommends concrete cost-optimization opportunities (rightsizing, autoscaling, "
        "reserved capacity, storage tiering, orphaned resources), in response to queries."
    ),
    tools=[
        load_drawio,
        load_master_process_json,
        load_requirements_summary,
        estimate_cloudarch_finops,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
    instruction_file="cloudarch/cloudarch_finops_agent.txt",
)
