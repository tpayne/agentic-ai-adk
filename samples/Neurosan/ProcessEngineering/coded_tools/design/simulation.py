"""Design-document analogue of coded_tools/process/simulation.py's Monte
Carlo process simulation. Ported near-verbatim from the ADK sample's
process_agents/design/design_simulation_agent.py (the pure-Python
functions only -- the ADK LlmAgent definitions at the bottom of that file
are replaced by this project's design.hocon/design_simulation_query.hocon
front-men).

The process schema gives a real numeric quantity to simulate
(process_steps[].estimated_duration + dependencies -> cycle time). The
design schema has no equivalent numeric field, so this module models a
different but equally schema-grounded question: "if a component fails, how
far does the damage spread, and which components are single points of
failure?" -- a blast-radius / cascading-failure Monte Carlo built entirely
from real schema fields:
  - high_level_design.components[].dependencies   (who relies on whom)
  - high_level_design.integration_points[]         (source/target links)
  - high_level_design.risks_and_mitigations[] /
    top-level risk_register[]                      (real likelihood/impact
                                                      enums)
  - high_level_design.availability_and_resilience.availability_target
    (e.g. "99.9%"), used as the baseline per-component failure probability
    when nothing more specific is known.

Nothing here fabricates data the schema doesn't have. If
high_level_design.components is absent entirely (a pure LLD-only
document), simulation is refused with an error rather than inventing a
graph.
"""

import json
import random
import re
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Set, Tuple

from coded_tools.common import paths
from coded_tools.common.design_json import load_master_design_json, extract_valid_json

SIM_RESULTS_FILENAME = "design_simulation_results.json"

# ============================================================
# SCHEMA-GROUNDED EXTRACTION HELPERS
# ============================================================

_LIKELIHOOD_BASE = {"low": 0.03, "medium": 0.08, "high": 0.18}
_IMPACT_MULTIPLIER = {"low": 0.5, "medium": 1.0, "high": 2.0}
_DEFAULT_BASELINE_FAILURE_PROB = 0.01  # used only if availability_target is absent/unparseable


def _availability_target_to_baseline_prob(hld: Dict[str, Any]) -> float:
    """Parses high_level_design.availability_and_resilience.availability_target
    (e.g. "99.9%") into a baseline per-component failure probability
    (1 - target/100). Falls back to a flat default if missing/unparseable."""
    availability = (
        (hld.get("availability_and_resilience") or {}).get("availability_target")
        if isinstance(hld, dict) else None
    )
    if not availability:
        return _DEFAULT_BASELINE_FAILURE_PROB

    match = re.search(r"(\d+(?:\.\d+)?)\s*%", str(availability))
    if not match:
        return _DEFAULT_BASELINE_FAILURE_PROB

    try:
        pct = float(match.group(1))
        pct = max(0.0, min(100.0, pct))
        return max(0.0005, 1.0 - (pct / 100.0))
    except Exception:
        return _DEFAULT_BASELINE_FAILURE_PROB


def _gather_components(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Components with a real dependency graph only exist under
    high_level_design.components (componentSpec has "dependencies");
    low_level_design.components have no such field, so a pure-LLD
    document is not simulatable -- callers must treat an empty return as
    a hard error, not a fallback."""
    hld = data.get("high_level_design") or {}
    components = hld.get("components")
    if isinstance(components, list):
        return [c for c in components if isinstance(c, dict) and c.get("component_name")]
    return []


def _gather_integration_edges(hld: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges = hld.get("integration_points")
    return edges if isinstance(edges, list) else []


def _gather_risk_items(data: Dict[str, Any], hld: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Combines high_level_design.risks_and_mitigations with the top-level
    risk_register, deduped by id (or description) so a risk recorded in
    both places isn't reported twice."""
    items = []
    seen = set()
    for source in (hld.get("risks_and_mitigations"), data.get("risk_register")):
        if not isinstance(source, list):
            continue
        for r in source:
            if not isinstance(r, dict):
                continue
            key = r.get("id") or r.get("description")
            if key in seen:
                continue
            seen.add(key)
            items.append(r)
    return items


def _risk_added_probability(component_name: str, risk_items: List[Dict[str, Any]]) -> float:
    """Case-insensitive substring match of the component name against each
    risk's free-text fields. Matched risks add probability based on their
    real likelihood/impact enums; unmatched risks contribute nothing."""
    name_lower = component_name.lower().strip()
    if not name_lower:
        return 0.0

    added = 0.0
    for risk in risk_items:
        haystack = " ".join(
            str(risk.get(field, "")) for field in ("description", "mitigation", "id", "category")
        ).lower()
        if name_lower in haystack:
            likelihood = str(risk.get("likelihood", "medium")).lower()
            impact = str(risk.get("impact", "medium")).lower()
            added += _LIKELIHOOD_BASE.get(likelihood, 0.05) * _IMPACT_MULTIPLIER.get(impact, 1.0)

    return added


_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "via", "at", "by",
}


def _tokenize_name(name: str) -> Set[str]:
    """Lowercase, punctuation-agnostic word set for fuzzy component-name matching."""
    tokens = re.split(r"[^a-z0-9]+", name.lower())
    return {t for t in tokens if t and t not in _STOPWORDS and len(t) > 1}


def _resolve_component_reference(
    ref: str, name_set: List[str], name_tokens: Dict[str, Set[str]]
) -> Optional[str]:
    """Resolves a dependency/integration-point endpoint string to a known
    component_name, tolerating naming drift between LLM-authored sections
    of the same document. Exact match wins outright. Otherwise scores every
    component by what fraction of the REFERENCE's own tokens it contains,
    accepting the best match only if it's a strong (>=0.75), unambiguous
    (beats the runner-up by >=0.15) subset match -- an ambiguous reference
    is deliberately left unresolved rather than guessed."""
    if ref in name_set:
        return ref

    ref_tokens = _tokenize_name(ref)
    if not ref_tokens:
        return None

    scored = []
    for name in name_set:
        overlap = len(ref_tokens & name_tokens[name]) / len(ref_tokens)
        scored.append((overlap, name))
    scored.sort(reverse=True)

    if not scored or scored[0][0] < 0.75:
        return None
    if len(scored) > 1 and (scored[0][0] - scored[1][0]) < 0.15:
        return None  # ambiguous between two+ components -- don't guess

    return scored[0][1]


def _build_impacts_graph(
    comp_names: List[str], components: List[Dict[str, Any]], integration_edges: List[Dict[str, Any]]
) -> Tuple[Dict[str, Set[str]], Set[str]]:
    """Builds a reverse-dependency ("if X fails, who is impacted") graph
    from componentSpec.dependencies and integration_points source/target
    pairs. Endpoints unresolved by _resolve_component_reference are
    recorded in `unresolved` rather than silently dropped or fabricated."""
    name_tokens = {n: _tokenize_name(n) for n in comp_names}
    impacts: Dict[str, Set[str]] = {n: set() for n in comp_names}
    unresolved: Set[str] = set()

    def resolve(ref: str) -> Optional[str]:
        return _resolve_component_reference(ref, comp_names, name_tokens)

    for c in components:
        name = c.get("component_name")
        if not name:
            continue
        for dep in (c.get("dependencies") or []):
            dep = str(dep).strip()
            if not dep:
                continue
            resolved = resolve(dep)
            if resolved:
                impacts[resolved].add(name)
            else:
                unresolved.add(dep)

    for edge in integration_edges:
        if not isinstance(edge, dict):
            continue
        src_raw, tgt_raw = edge.get("source"), edge.get("target")
        src = resolve(str(src_raw)) if src_raw else None
        tgt = resolve(str(tgt_raw)) if tgt_raw else None
        if src and tgt:
            impacts[tgt].add(src)
        else:
            if tgt_raw and not tgt:
                unresolved.add(str(tgt_raw))
            if src_raw and not src:
                unresolved.add(str(src_raw))

    return impacts, unresolved


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


# ============================================================
# CORE MONTE CARLO BLAST-RADIUS SIMULATION
# ============================================================

def _run_core_design_simulation(
    data: Dict[str, Any],
    iterations: int = 2000,
    overrides: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Monte Carlo blast-radius simulation (see module docstring). Each of
    `iterations` trials independently fails every component per its own
    baseline-plus-risk-adjusted probability, expands that seed set through
    the impacts graph, and records the resulting fraction of the
    architecture affected; aggregating across trials yields the average/
    variance blast radius and a "critical incident" rate (trials where
    >=50% of the architecture was affected) that drive the Low/Medium/High
    resilience_risk_rating. single_points_of_failure is ranked by each
    component's own isolated blast radius times its failure probability --
    deterministic, not a simulation outcome. `overrides` lets a caller pin
    specific components' failure probability instead of the derived
    baseline (used by the sensitivity analysis below)."""
    hld = data.get("high_level_design") or {}
    components = _gather_components(data)
    if not components:
        raise ValueError(
            'No valid "high_level_design.components" array with dependency data found. '
            "A pure Low-Level Design document has no component dependency graph to simulate."
        )

    comp_names = [c["component_name"] for c in components]
    baseline_prob = _availability_target_to_baseline_prob(hld)
    risk_items = _gather_risk_items(data, hld)
    integration_edges = _gather_integration_edges(hld)

    comp_prob: Dict[str, float] = {}
    for name in comp_names:
        p = baseline_prob + _risk_added_probability(name, risk_items)
        if overrides and name in overrides:
            p = overrides[name]
        comp_prob[name] = max(0.0, min(0.9, p))

    impacts, unresolved = _build_impacts_graph(comp_names, components, integration_edges)
    total = len(comp_names)

    isolated_blast = {
        name: len(_blast_radius({name}, impacts)) / max(1, total) for name in comp_names
    }

    blast_fractions: List[float] = []
    critical_hits = 0

    for _ in range(iterations):
        failed = {name for name in comp_names if random.random() < comp_prob.get(name, baseline_prob)}
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
        comp_names, key=lambda n: (isolated_blast.get(n, 0.0), comp_prob.get(n, 0.0)), reverse=True
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
        "single_points_of_failure": single_points_of_failure,
        "per_component_failure_probability": comp_prob,
        "component_count": total,
        "unresolved_references": sorted(unresolved),
    }


def _persist_design_simulation_metrics(metrics: Dict[str, Any]) -> None:
    with open(paths.output_path(SIM_RESULTS_FILENAME), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)


# ============================================================
# SCALABILITY ANALYSIS
# ============================================================
# Grounded in high_level_design.scalability_and_performance plus a
# structural signal the resilience graph already gives for free: fan-in
# (how many other components depend on this one) is exactly what "load
# concentration" means architecturally. A high fan-in component with no
# declared scaling strategy and no elastic-sounding tech in its own stack
# is a real, defensible bottleneck candidate -- not a numeric load
# prediction (the schema has no traffic/throughput figures), but an honest
# structural flag.

_ELASTIC_TECH_KEYWORDS = (
    "kubernetes", "k8s", "auto-scal", "autoscal", "serverless", "lambda",
    "fargate", "elastic", "horizontal", "cloud run", "app engine",
)
_SCALABILITY_RISK_KEYWORDS = (
    "scal", "load", "capacity", "throughput", "performance", "traffic", "concurren",
)


def _analyze_scalability(
    data: Dict[str, Any], hld: Dict[str, Any], components: List[Dict[str, Any]], impacts: Dict[str, Set[str]]
) -> Dict[str, Any]:
    perf = hld.get("scalability_and_performance") or {}
    risk_items = _gather_risk_items(data, hld)

    structural_bottlenecks = []
    for c in components:
        name = c.get("component_name")
        if not name:
            continue
        fan_in = len(impacts.get(name, ()))
        if fan_in < 2:
            continue
        stack_text = " ".join(str(t) for t in (c.get("technology_stack") or [])).lower()
        has_elastic_tech = any(kw in stack_text for kw in _ELASTIC_TECH_KEYWORDS)
        if not has_elastic_tech:
            structural_bottlenecks.append({
                "component_name": name,
                "dependent_count": fan_in,
                "elastic_technology_declared": False,
            })

    structural_bottlenecks.sort(key=lambda x: x["dependent_count"], reverse=True)

    flagged_risks = [
        {"id": r.get("id"), "description": r.get("description"), "likelihood": r.get("likelihood"), "impact": r.get("impact")}
        for r in risk_items
        if any(kw in " ".join(str(r.get(f, "")) for f in ("description", "category")).lower() for kw in _SCALABILITY_RISK_KEYWORDS)
    ]

    return {
        "expected_load": perf.get("expected_load"),
        "scaling_strategy_declared": bool(perf.get("scaling_strategy")),
        "scaling_strategy": perf.get("scaling_strategy"),
        "performance_targets": perf.get("performance_targets") or [],
        "structural_bottlenecks": structural_bottlenecks[:3],
        "flagged_risks": flagged_risks,
    }


# ============================================================
# SECURITY ANALYSIS
# ============================================================
# Grounded in high_level_design.security_architecture (a coverage check --
# which controls are documented at all) and the real compliance_status
# enums under compliance_and_standards.applicable_standards /
# security_architecture.compliance_standards, plus any risk items whose
# category/description reads as security-related.

_SECURITY_RISK_KEYWORDS = (
    "security", "breach", "auth", "access", "encrypt", "vulnerab", "data protection", "privacy",
)
_NON_COMPLIANT_STATUSES = {"non_compliant", "partially_compliant"}


def _analyze_security(data: Dict[str, Any], hld: Dict[str, Any]) -> Dict[str, Any]:
    sec = hld.get("security_architecture") or {}
    risk_items = _gather_risk_items(data, hld)

    control_fields = [
        ("authentication_mechanism", "Authentication mechanism"),
        ("authorization_model", "Authorization model"),
        ("data_protection_measures", "Data protection measures"),
        ("threat_model_reference", "Threat model reference"),
    ]
    missing_controls = [label for field, label in control_fields if not sec.get(field)]

    compliance_items = list(sec.get("compliance_standards") or [])
    compliance_items += list((data.get("compliance_and_standards") or {}).get("applicable_standards") or [])

    compliance_summary: Dict[str, int] = {}
    non_compliant_standards = []
    for item in compliance_items:
        if not isinstance(item, dict):
            continue
        status = item.get("compliance_status", "under_review")
        compliance_summary[status] = compliance_summary.get(status, 0) + 1
        if status in _NON_COMPLIANT_STATUSES:
            non_compliant_standards.append({
                "standard_name": item.get("standard_name"),
                "compliance_status": status,
            })

    flagged_risks = [
        {"id": r.get("id"), "description": r.get("description"), "likelihood": r.get("likelihood"), "impact": r.get("impact")}
        for r in risk_items
        if any(kw in " ".join(str(r.get(f, "")) for f in ("description", "category")).lower() for kw in _SECURITY_RISK_KEYWORDS)
    ]

    external_systems = (data.get("system_context") or {}).get("external_systems") or []
    external_exposure_without_full_controls = bool(external_systems) and bool(missing_controls)

    security_risk_rating = "Low"
    if non_compliant_standards or (external_exposure_without_full_controls and len(missing_controls) >= 2):
        security_risk_rating = "High"
    elif missing_controls or flagged_risks:
        security_risk_rating = "Medium"

    return {
        "missing_controls": missing_controls,
        "compliance_summary": compliance_summary,
        "non_compliant_standards": non_compliant_standards,
        "flagged_risks": flagged_risks,
        "external_exposure_without_full_controls": external_exposure_without_full_controls,
        "security_risk_rating": security_risk_rating,
    }


# ============================================================
# LATENCY ANALYSIS
# ============================================================
# Grounded in quality_attributes entries tagged "performance_efficiency"
# (the only place the schema records a latency-style metric/target) plus
# the dependency graph's longest chain -- the schema has no per-hop
# latency figure, so a long undeclared chain is reported as a latency-
# BUDGET-RISK flag, not a fabricated number.

_LATENCY_VALUE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|milliseconds|s\b|sec|seconds)", re.IGNORECASE)


def _build_depends_on_graph(comp_names: List[str], impacts: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """Forward view of the impacts graph: depends_on[x] = things x relies on."""
    depends_on: Dict[str, Set[str]] = {n: set() for n in comp_names}
    for dep, dependents in impacts.items():
        for dependent in dependents:
            depends_on.setdefault(dependent, set()).add(dep)
    return depends_on


def _deepest_chain(comp_names: List[str], depends_on: Dict[str, Set[str]]) -> List[str]:
    """Longest simple dependency chain (cycle-safe) via DFS from every node."""
    best: List[str] = []

    def dfs(node: str, path: List[str], visited: Set[str]):
        nonlocal best
        if len(path) > len(best):
            best = list(path)
        for dep in depends_on.get(node, ()):
            if dep not in visited:
                dfs(dep, path + [dep], visited | {dep})

    for start in comp_names:
        dfs(start, [start], {start})

    return best


def _analyze_latency(
    data: Dict[str, Any], comp_names: List[str], impacts: Dict[str, Set[str]]
) -> Dict[str, Any]:
    quality_attributes = data.get("quality_attributes") or []
    perf_qas = [
        qa for qa in quality_attributes
        if isinstance(qa, dict) and qa.get("characteristic") == "performance_efficiency" and qa.get("target")
    ]
    declared_targets = [
        {"metric": qa.get("metric"), "target": qa.get("target")} for qa in perf_qas
    ]
    parsed_values = []
    for qa in perf_qas:
        m = _LATENCY_VALUE_RE.search(str(qa.get("target", "")))
        if m:
            parsed_values.append(f"{m.group(1)}{m.group(2)}")

    depends_on = _build_depends_on_graph(comp_names, impacts)
    chain = _deepest_chain(comp_names, depends_on)

    latency_budget_risk = len(chain) >= 3 and not declared_targets

    return {
        "declared_latency_targets": declared_targets,
        "parsed_latency_values": parsed_values,
        "deepest_dependency_chain_length": len(chain),
        "deepest_dependency_chain": chain,
        "latency_budget_risk": latency_budget_risk,
    }


def _resolve_input_data(design_json_str) -> Dict[str, Any]:
    """Resolves the design document to simulate, without depending on the
    LLM faithfully retyping the entire document as a function-call
    argument (a real HLD/LLD/Combined document easily runs to tens of
    thousands of characters -- asking a model to reproduce that verbatim
    is exactly the kind of thing that silently truncates mid-document).
    Precedence: an already-parsed non-empty dict; else a non-empty string
    that parses as valid JSON; else loaded fresh from disk via
    load_master_design_json() -- the expected path, since the tool call
    normally omits this argument entirely."""
    if isinstance(design_json_str, dict) and design_json_str:
        return design_json_str

    if design_json_str:
        parsed = extract_valid_json(str(design_json_str).strip())
        if parsed is not None:
            return parsed

    data = load_master_design_json()
    if not data:
        raise ValueError(
            "No design document data available -- neither a usable argument was "
            "provided nor is output/design_data.json present on disk."
        )
    return data


# ============================================================
# TOOL: COMPOSITE SIMULATION (resilience + scalability + security + latency)
# ============================================================

def simulate_design_architecture(design_json_str=None) -> str:
    """Runs all four dimensions against the same design document in one
    call: resilience (Monte Carlo blast radius), scalability (structural
    bottleneck + declared-strategy check), security (control coverage +
    real compliance_status enums), and latency (declared performance
    targets + longest undeclared dependency chain). The argument is
    optional -- see _resolve_input_data; the normal path is to call this
    with no argument, since the tool loads the current design itself."""
    try:
        data = _resolve_input_data(design_json_str)
        resilience = _run_core_design_simulation(data, iterations=2000)

        hld = data.get("high_level_design") or {}
        components = _gather_components(data)
        comp_names = [c["component_name"] for c in components]
        integration_edges = _gather_integration_edges(hld)
        impacts, _unresolved = _build_impacts_graph(comp_names, components, integration_edges)

        scalability = _analyze_scalability(data, hld, components, impacts)
        security = _analyze_security(data, hld)
        latency = _analyze_latency(data, comp_names, impacts)

        ratings = [resilience.get("resilience_risk_rating"), security.get("security_risk_rating")]
        if scalability.get("structural_bottlenecks"):
            ratings.append("Medium")
        if latency.get("latency_budget_risk"):
            ratings.append("Medium")
        overall_risk_rating = "High" if "High" in ratings else ("Medium" if "Medium" in ratings else "Low")

        result = {
            "resilience": resilience,
            "scalability": scalability,
            "security": security,
            "latency": latency,
            "overall_risk_rating": overall_risk_rating,
        }
        _persist_design_simulation_metrics(result)
        return json.dumps(result)

    except Exception as e:
        return json.dumps({"error": "design_simulation_failed", "detail": str(e)})


# ============================================================
# TOOL: SENSITIVITY ANALYSIS (which component most needs redundancy)
# ============================================================

def perform_design_sensitivity_analysis(design_json_str=None) -> str:
    """For each component, re-runs the simulation with that component's
    failure probability driven near zero ("what if this component were
    made fully redundant"), and ranks components by how much that reduces
    the average blast radius -- the design-side equivalent of
    coded_tools/process/simulation.py's perform_sensitivity_analysis. The
    argument is optional -- see _resolve_input_data."""
    try:
        data = _resolve_input_data(design_json_str)
        baseline = _run_core_design_simulation(data, iterations=500)
        base_blast = baseline["avg_blast_radius"]

        components = _gather_components(data)
        impact_results = []

        for c in components:
            name = c.get("component_name")
            if not name:
                continue
            sim = _run_core_design_simulation(data, iterations=500, overrides={name: 0.001})
            improvement = base_blast - sim["avg_blast_radius"]
            impact_results.append({
                "component_name": name,
                "blast_radius_reduction": improvement,
                "new_avg_blast_radius": sim["avg_blast_radius"],
            })

        impact_results.sort(key=lambda x: x["blast_radius_reduction"], reverse=True)
        top_leverage = impact_results[0] if impact_results else {}

        return json.dumps({
            "baseline_avg_blast_radius": base_blast,
            "top_leverage_component": top_leverage.get("component_name"),
            "potential_blast_radius_reduction": top_leverage.get("blast_radius_reduction"),
            "full_analysis": impact_results[:3],
        })

    except Exception as e:
        return json.dumps({"error": str(e)})
