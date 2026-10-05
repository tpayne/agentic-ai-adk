"""CloudArch diagram simulation: structural resilience (Monte Carlo blast
radius), scalability (fan-in bottleneck), and latency (deepest dependency
chain), derived purely from the diagram's own vertices/edges.

Ported near-verbatim from the ADK sample's cloudarch_simulation_agent.py --
pure Python, nothing ADK-specific.
"""

import json
import random
import re
from statistics import mean, pstdev
from typing import Any, Dict, List, Set

from coded_tools.cloudarch.drawio_graph import parse_drawio_graph
from coded_tools.common.drawio_persistence import load_drawio_xml
from coded_tools.common.master_json import load_master_json
from coded_tools.common.paths import output_path

_DEFAULT_BASELINE_FAILURE_PROB = 0.02

_ELASTIC_SHAPE_KEYWORDS = (
    "lambda", "fargate", "ecs", "eks", "auto_scaling", "autoscaling",
    "kubernetes_engine", "aks", "gke", "cloud_run", "app_engine",
    "cloud_functions", "functions", "elastic_beanstalk", "app_service",
    "container_apps", "serverless",
)

_RISK_STOPWORDS = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "via", "at", "by"}


def _tokenize(text: str) -> Set[str]:
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return {t for t in tokens if t and t not in _RISK_STOPWORDS and len(t) > 1}


def _build_impacts_graph(vertices: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    vertex_ids = {v["id"] for v in vertices}
    impacts: Dict[str, Set[str]] = {vid: set() for vid in vertex_ids}
    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if src in vertex_ids and tgt in vertex_ids:
            impacts[tgt].add(src)
    return impacts


def _blast_radius(failed: Set[str], impacts: Dict[str, Set[str]]) -> Set[str]:
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


def _gather_risk_items(context_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(context_data, dict):
        return []
    items = []
    hld = context_data.get("high_level_design") or {}
    for source in (hld.get("risks_and_mitigations"), context_data.get("risk_register")):
        if isinstance(source, list):
            items.extend(r for r in source if isinstance(r, dict))
    return items


def _run_core_simulation(
    vertices: List[Dict[str, Any]], edges: List[Dict[str, Any]], risk_items: List[Dict[str, Any]], iterations: int = 2000
) -> Dict[str, Any]:
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

    isolated_blast = {vid: len(_blast_radius({vid}, impacts)) / max(1, total) for vid in vertex_ids}

    blast_fractions: List[float] = []
    critical_hits = 0
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
        "single_points_of_failure": [{"id": vid, "value": value_by_id.get(vid)} for vid in single_points_of_failure],
        "component_count": total,
    }


def _analyze_scalability(vertices: List[Dict[str, Any]], impacts: Dict[str, Set[str]]) -> Dict[str, Any]:
    structural_bottlenecks = []
    for v in vertices:
        vid = v["id"]
        fan_in = len(impacts.get(vid, ()))
        if fan_in < 2:
            continue
        has_elastic_tech = any(kw in v["shape_slug"].lower() for kw in _ELASTIC_SHAPE_KEYWORDS)
        if not has_elastic_tech:
            structural_bottlenecks.append({
                "id": vid, "value": v["value"], "dependent_count": fan_in, "elastic_technology_detected": False,
            })
    structural_bottlenecks.sort(key=lambda x: x["dependent_count"], reverse=True)
    return {"structural_bottlenecks": structural_bottlenecks[:3]}


def _build_depends_on_graph(vertex_ids: List[str], impacts: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    depends_on: Dict[str, Set[str]] = {vid: set() for vid in vertex_ids}
    for dep, dependents in impacts.items():
        for dependent in dependents:
            depends_on.setdefault(dependent, set()).add(dep)
    return depends_on


def _deepest_chain(vertex_ids: List[str], depends_on: Dict[str, Set[str]]) -> List[str]:
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


def _persist_metrics(metrics: Dict[str, Any]) -> None:
    try:
        with open(output_path("cloudarch_simulation_results.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def simulate_cloudarch_architecture(xml_content: Any = None) -> str:
    try:
        if not xml_content:
            loaded = load_drawio_xml()
            if loaded.get("status") != "OK" or not loaded.get("xml"):
                return json.dumps({"error": "no_diagram_available", "detail": "No cloud architecture diagram has been saved yet."})
            xml_content = loaded["xml"]

        graph = parse_drawio_graph(xml_content)
        vertices, edges = graph["vertices"], graph["edges"]

        risk_items = _gather_risk_items(load_master_json())

        resilience = _run_core_simulation(vertices, edges, risk_items, iterations=2000)
        impacts = _build_impacts_graph(vertices, edges)
        scalability = _analyze_scalability(vertices, impacts)
        latency = _analyze_latency(vertices, impacts)

        ratings = [resilience.get("resilience_risk_rating")]
        if scalability.get("structural_bottlenecks"):
            ratings.append("Medium")
        if latency.get("latency_budget_risk"):
            ratings.append("Medium")
        overall_risk_rating = "High" if "High" in ratings else ("Medium" if "Medium" in ratings else "Low")

        result = {"resilience": resilience, "scalability": scalability, "latency": latency, "overall_risk_rating": overall_risk_rating}
        _persist_metrics(result)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": "cloudarch_simulation_failed", "detail": str(e)})
