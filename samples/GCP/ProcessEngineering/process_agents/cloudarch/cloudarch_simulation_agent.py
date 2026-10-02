# process_agents/cloudarch_simulation_agent.py
#
# CloudArch analogue of design_simulation_agent.py's composite simulation,
# but grounded in the drawio/mxGraph diagram itself rather than the source
# design document's JSON schema. The diagram is often the more granular
# artifact -- it can carry WAF/KMS/IAM/CloudFront-level detail a design
# document's abstract `components` list never enumerates -- so simulating
# the diagram answers "what would actually break" more precisely than
# re-simulating the document it was generated from.
#
# Three structural dimensions, all derivable purely from the diagram's own
# vertices/edges (via utils.parse_drawio_graph) with no fabricated data:
#   - Resilience: Monte Carlo blast-radius over the vertex/edge graph,
#     same algorithm shape as design_simulation_agent._blast_radius.
#   - Scalability: fan-in bottleneck detection, cross-checked against a
#     small "does this look like an elastic-scaling service" keyword list
#     matched on each vertex's shape_slug (the drawio equivalent of
#     design_simulation_agent's _ELASTIC_TECH_KEYWORDS check).
#   - Latency: deepest dependency chain length (structural only -- a
#     diagram has no declared numeric latency targets to cross-check
#     against, unlike the design document's quality_attributes).
#
# A security-control-coverage dimension (WAF/KMS/IAM/GuardDuty presence) is
# deliberately NOT included: unlike scalability's small elastic-tech list,
# a security catalog would need to span many more service families across
# three cloud providers with real false-negative risk, and no existing
# shape-to-concept catalog in this codebase could be leaned on for it. Left
# as a clean, explicitly scoped-out follow-up rather than a rushed guess.

import json
import logging
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Set

import random

from google.genai import types

from ..common.utils import load_drawio, load_master_process_json, parse_drawio_graph

logger = logging.getLogger("ProcessArchitect.CloudArchSimulation")

CLOUDARCH_SIM_RESULTS_PATH = "output/cloudarch_simulation_results.json"

_DEFAULT_BASELINE_FAILURE_PROB = 0.02

_ELASTIC_SHAPE_KEYWORDS = (
    "lambda", "fargate", "ecs", "eks", "auto_scaling", "autoscaling",
    "kubernetes_engine", "aks", "gke", "cloud_run", "app_engine",
    "cloud_functions", "functions", "elastic_beanstalk", "app_service",
    "container_apps", "serverless",
)

_RISK_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "via", "at", "by",
}


def _tokenize(text: str) -> Set[str]:
    import re
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return {t for t in tokens if t and t not in _RISK_STOPWORDS and len(t) > 1}


def _build_impacts_graph(
    vertices: List[Dict[str, Any]], edges: List[Dict[str, Any]]
) -> Dict[str, Set[str]]:
    """
    Reverse-dependency ("if X fails, who is impacted") graph, keyed by
    vertex id. Unlike design_simulation_agent's equivalent, edge
    source/target here are already real vertex ids (the diagram's own
    mxCell references), so no fuzzy name resolution is needed: an edge
    source -> target means "source calls target", so if target fails,
    source is impacted.
    """
    vertex_ids = {v["id"] for v in vertices}
    impacts: Dict[str, Set[str]] = {vid: set() for vid in vertex_ids}
    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if src in vertex_ids and tgt in vertex_ids:
            impacts[tgt].add(src)
    return impacts


def _blast_radius(failed: Set[str], impacts: Dict[str, Set[str]]) -> Set[str]:
    """BFS over the impacts graph from an initial failed set."""
    affected = set(failed)
    frontier = list(failed)
    while frontier:
        node = frontier.pop()
        for dependent in impacts.get(node, ()):
            if dependent not in affected:
                affected.add(dependent)
                frontier.append(dependent)
    return affected


def _risk_added_probability(vertex_value: str, risk_items: List[Dict[str, Any]]) -> float:
    """
    Best-effort, optional enrichment: if a process/design document with a
    risk_register happens to be available, bump a vertex's baseline failure
    probability when its label fuzzy-matches a real risk item's free text.
    Never required -- absent risk data simply means every vertex keeps the
    flat baseline, never a fabricated one.
    """
    _LIKELIHOOD_BASE = {"low": 0.03, "medium": 0.08, "high": 0.18}
    _IMPACT_MULTIPLIER = {"low": 0.5, "medium": 1.0, "high": 2.0}

    value_tokens = _tokenize(vertex_value)
    if not value_tokens:
        return 0.0

    added = 0.0
    for risk in risk_items:
        if not isinstance(risk, dict):
            continue
        haystack = " ".join(str(risk.get(f, "")) for f in ("description", "mitigation", "id", "category"))
        risk_tokens = _tokenize(haystack)
        if value_tokens & risk_tokens:
            likelihood = str(risk.get("likelihood", "medium")).lower()
            impact = str(risk.get("impact", "medium")).lower()
            added += _LIKELIHOOD_BASE.get(likelihood, 0.05) * _IMPACT_MULTIPLIER.get(impact, 1.0)
    return added


def _gather_risk_items(context_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pulls whatever risk entries exist in a loaded process/design context
    (high_level_design.risks_and_mitigations and/or a top-level
    risk_register), for _risk_added_probability to optionally match
    against. Returns [] if there's nothing usable -- never required."""
    if not isinstance(context_data, dict):
        return []
    items = []
    hld = context_data.get("high_level_design") or {}
    for source in (hld.get("risks_and_mitigations"), context_data.get("risk_register")):
        if isinstance(source, list):
            items.extend(r for r in source if isinstance(r, dict))
    return items


def _run_core_cloudarch_simulation(
    vertices: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    risk_items: List[Dict[str, Any]],
    iterations: int = 2000,
) -> Dict[str, Any]:
    """
    Monte Carlo resilience simulation: each of `iterations` trials
    independently fails every vertex per its own baseline (+ risk-adjusted)
    probability, expands that seed set through the impacts graph via
    _blast_radius, and records the resulting fraction of the diagram
    affected. Aggregating across trials yields an average/variance blast
    radius and a "critical incident" rate (trials where >=50% of the
    diagram was affected), which together drive the Low/Medium/High
    resilience_risk_rating. single_points_of_failure ranks vertices by
    their OWN isolated blast radius (if only this one thing failed) times
    its failure probability, not by simulation outcome alone.
    """
    if not vertices:
        raise ValueError(
            "No simulatable service nodes found in the diagram (vertices with a "
            "shape=mxgraph.<provider>.<name> icon token). Generate a diagram first."
        )

    vertex_ids = [v["id"] for v in vertices]
    value_by_id = {v["id"]: v["value"] for v in vertices}
    impacts = _build_impacts_graph(vertices, edges)
    total = len(vertex_ids)

    comp_prob: Dict[str, float] = {}
    for vid in vertex_ids:
        p = _DEFAULT_BASELINE_FAILURE_PROB + _risk_added_probability(value_by_id[vid], risk_items)
        comp_prob[vid] = max(0.0, min(0.9, p))

    isolated_blast = {
        vid: len(_blast_radius({vid}, impacts)) / max(1, total) for vid in vertex_ids
    }

    blast_fractions: List[float] = []
    critical_hits = 0
    # Each trial samples independent component failures; the impacts graph
    # expands those seeds to include every transitively affected service.
    for _ in range(iterations):
        failed = {vid for vid in vertex_ids if random.random() < comp_prob.get(vid, _DEFAULT_BASELINE_FAILURE_PROB)}
        if not failed:
            blast_fractions.append(0.0)
            continue
        affected = _blast_radius(failed, impacts)
        frac = len(affected) / max(1, total)
        blast_fractions.append(frac)
        if frac >= 0.5:
            critical_hits += 1

    avg_blast = float(mean(blast_fractions)) if blast_fractions else 0.0
    variance = float(pstdev(blast_fractions)) if len(blast_fractions) > 1 else 0.0
    critical_incident_rate = (critical_hits / iterations) if iterations else 0.0

    single_points_of_failure = sorted(
        vertex_ids, key=lambda vid: (isolated_blast.get(vid, 0.0), comp_prob.get(vid, 0.0)), reverse=True
    )[:3]

    resilience_risk_rating = "Low"
    if avg_blast > 0.35 or critical_incident_rate > 0.15:
        resilience_risk_rating = "High"
    elif avg_blast > 0.15 or critical_incident_rate > 0.05:
        resilience_risk_rating = "Medium"

    return {
        "avg_blast_radius": avg_blast,
        "blast_radius_variance": variance,
        "critical_incident_rate": critical_incident_rate,
        "resilience_risk_rating": resilience_risk_rating,
        "single_points_of_failure": [
            {"id": vid, "value": value_by_id.get(vid)} for vid in single_points_of_failure
        ],
        "per_component_failure_probability": {value_by_id.get(vid, vid): p for vid, p in comp_prob.items()},
        "component_count": total,
    }


def _analyze_scalability(
    vertices: List[Dict[str, Any]], impacts: Dict[str, Set[str]]
) -> Dict[str, Any]:
    structural_bottlenecks = []
    for v in vertices:
        vid = v["id"]
        fan_in = len(impacts.get(vid, ()))
        if fan_in < 2:
            continue
        has_elastic_tech = any(kw in v["shape_slug"].lower() for kw in _ELASTIC_SHAPE_KEYWORDS)
        if not has_elastic_tech:
            structural_bottlenecks.append({
                "id": vid,
                "value": v["value"],
                "dependent_count": fan_in,
                "elastic_technology_detected": False,
            })
    structural_bottlenecks.sort(key=lambda x: x["dependent_count"], reverse=True)
    return {"structural_bottlenecks": structural_bottlenecks[:3]}


def _build_depends_on_graph(vertex_ids: List[str], impacts: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """Forward view of the impacts graph: depends_on[x] = things x relies on."""
    depends_on: Dict[str, Set[str]] = {vid: set() for vid in vertex_ids}
    for dep, dependents in impacts.items():
        for dependent in dependents:
            depends_on.setdefault(dependent, set()).add(dep)
    return depends_on


def _deepest_chain(vertex_ids: List[str], depends_on: Dict[str, Set[str]]) -> List[str]:
    """Longest simple dependency chain (cycle-safe) via DFS from every node."""
    best: List[str] = []

    def dfs(node: str, path: List[str], visited: Set[str]):
        nonlocal best
        if len(path) > len(best):
            best = list(path)
        for dep in depends_on.get(node, ()):
            if dep not in visited:
                dfs(dep, path + [dep], visited | {dep})

    for start in vertex_ids:
        dfs(start, [start], {start})
    return best


def _analyze_latency(vertices: List[Dict[str, Any]], impacts: Dict[str, Set[str]]) -> Dict[str, Any]:
    vertex_ids = [v["id"] for v in vertices]
    value_by_id = {v["id"]: v["value"] for v in vertices}
    depends_on = _build_depends_on_graph(vertex_ids, impacts)
    chain = _deepest_chain(vertex_ids, depends_on)
    return {
        "deepest_dependency_chain_length": len(chain),
        "deepest_dependency_chain": [value_by_id.get(vid, vid) for vid in chain],
        "latency_budget_risk": len(chain) >= 4,
    }


def _persist_cloudarch_simulation_metrics(metrics: Dict[str, Any]) -> None:
    try:
        import os
        os.makedirs("output", exist_ok=True)
        with open(CLOUDARCH_SIM_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        logger.debug(f"CloudArch simulation metrics saved to {CLOUDARCH_SIM_RESULTS_PATH}")
    except Exception:
        logger.exception("Failed to persist CloudArch simulation metrics.")


def simulate_cloudarch_architecture(xml_content: Optional[str] = None) -> str:
    """
    Runs resilience (Monte Carlo blast radius), scalability (fan-in
    bottleneck + elastic-tech check), and latency (deepest dependency
    chain) analysis against the current cloud architecture diagram. The
    argument is optional: the normal path is to call this with no
    argument at all, since the tool loads the current diagram itself via
    load_drawio if none is passed.
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

        context_data = load_master_process_json()
        risk_items = _gather_risk_items(context_data)

        resilience = _run_core_cloudarch_simulation(vertices, edges, risk_items, iterations=2000)
        impacts = _build_impacts_graph(vertices, edges)
        scalability = _analyze_scalability(vertices, impacts)
        latency = _analyze_latency(vertices, impacts)

        ratings = [resilience.get("resilience_risk_rating")]
        if scalability.get("structural_bottlenecks"):
            ratings.append("Medium")
        if latency.get("latency_budget_risk"):
            ratings.append("Medium")
        overall_risk_rating = "High" if "High" in ratings else ("Medium" if "Medium" in ratings else "Low")

        result = {
            "resilience": resilience,
            "scalability": scalability,
            "latency": latency,
            "overall_risk_rating": overall_risk_rating,
        }
        _persist_cloudarch_simulation_metrics(result)
        return json.dumps(result)

    except Exception as e:
        logger.exception("CloudArch architecture simulation failed.")
        return json.dumps({
            "error": "cloudarch_simulation_failed",
            "detail": str(e),
        })


# ============================================================
# LLM AGENT: CLOUDARCH SIMULATION QUERY AGENT (ON-DEMAND, USER-FACING)
# ============================================================
# On-demand only, analogous to design_simulation_query_agent -- NOT wired
# as a pipeline-internal auto-revision gate. The user asked for the ability
# to run simulations against the diagram, not for generation to auto-block
# on results; adding a gate would be unrequested scope growth.
from ..common.agent_wrappers import ProcessLlmAgent

cloudarch_simulation_query_agent = ProcessLlmAgent(
    name="CloudArch_Simulation_Query_Agent",
    description=(
        "Runs a structural resilience (blast-radius Monte Carlo), scalability (fan-in bottleneck), and "
        "latency (dependency chain depth) simulation over an EXISTING cloud architecture diagram, in "
        "response to queries."
    ),
    tools=[
        load_drawio,
        load_master_process_json,
        simulate_cloudarch_architecture,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
    instruction_file="cloudarch/cloudarch_simulation_query_agent.txt",
)
