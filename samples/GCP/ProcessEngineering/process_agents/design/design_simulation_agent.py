# process_agents/design_simulation_agent.py
#
# Design-document analogue of simulation_agent.py's Monte Carlo process
# simulation. The process schema gives us a real numeric quantity to
# simulate (process_steps[].estimated_duration + dependencies -> cycle
# time). The design schema has no equivalent numeric field, so this
# module models a different but equally schema-grounded question:
# "if a component fails, how far does the damage spread, and which
# components are single points of failure?" -- a blast-radius / cascading
# -failure Monte Carlo built entirely from real schema fields:
#   - high_level_design.components[].dependencies   (who relies on whom)
#   - high_level_design.integration_points[]         (source/target links)
#   - high_level_design.risks_and_mitigations[] /
#     top-level risk_register[]                      (real likelihood/impact
#                                                       enums -- the closest
#                                                       thing the design
#                                                       schema has to a
#                                                       process step's
#                                                       estimated_duration)
#   - high_level_design.availability_and_resilience.availability_target
#     (e.g. "99.9%"), used as the baseline per-component failure
#     probability when nothing more specific is known.
#
# Nothing here fabricates data the schema doesn't have (there is no
# per-component uptime field, no load/traffic figures) -- it only combines
# fields that already exist. If high_level_design.components is absent
# entirely (a pure LLD-only document), simulation is refused with an
# error rather than inventing a graph.

import logging
import json
import random
import re
from statistics import mean, pstdev
from typing import Dict, Any, List, Optional, Set

from google.genai import types

from ..common.utils import (
    load_master_design_json,
    save_iteration_feedback,
    getProperty,
)

logger = logging.getLogger("ProcessArchitect.DesignSimulation")

DESIGN_SIM_RESULTS_PATH = "output/design_simulation_results.json"

# ============================================================
# JSON EXTRACTION + REPAIR (mirrors simulation_agent.py's helpers)
# ============================================================

def _attempt_json_repair(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
    cleaned = cleaned.replace("﻿", "")
    return cleaned


def _extract_valid_json(raw: str):
    raw = raw.strip()
    logger.debug(f"Raw LLM output received for design simulation (first 5000 chars): {raw[:5000]}")

    stack = []
    start_idx = None
    candidates = []

    for i, ch in enumerate(raw):
        if ch == "{":
            if not stack:
                start_idx = i
            stack.append("{")
        elif ch == "}":
            if stack:
                stack.pop()
                if not stack and start_idx is not None:
                    candidates.append(raw[start_idx:i + 1])
                    start_idx = None

    for block in sorted(candidates, key=len, reverse=True):
        try:
            return json.loads(block)
        except Exception:
            repaired = _attempt_json_repair(block)
            try:
                return json.loads(repaired)
            except Exception:
                continue

    raise ValueError(f"No valid JSON object found in LLM output {raw[:100]}.")


# ============================================================
# SCHEMA-GROUNDED EXTRACTION HELPERS
# ============================================================

_LIKELIHOOD_BASE = {"low": 0.03, "medium": 0.08, "high": 0.18}
_IMPACT_MULTIPLIER = {"low": 0.5, "medium": 1.0, "high": 2.0}
_DEFAULT_BASELINE_FAILURE_PROB = 0.01  # used only if availability_target is absent/unparseable


def _availability_target_to_baseline_prob(hld: Dict[str, Any]) -> float:
    """
    Parses high_level_design.availability_and_resilience.availability_target
    (e.g. "99.9%") into a baseline per-component failure probability
    (1 - target/100). Falls back to a flat default if missing or
    unparseable -- the design-side equivalent of process simulation's
    "estimated_duration defaults to 1 if missing".
    """
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
    """
    Components with a real dependency graph only exist under
    high_level_design.components (componentSpec has "dependencies").
    low_level_design.components exist but have no "dependencies" field
    in the schema, so they can't participate in the blast-radius graph;
    a pure-LLD document is therefore not simulatable and callers must
    treat an empty return as a hard error, not a fallback.
    """
    hld = data.get("high_level_design") or {}
    components = hld.get("components")
    if isinstance(components, list):
        return [c for c in components if isinstance(c, dict) and c.get("component_name")]
    return []


def _gather_integration_edges(hld: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges = hld.get("integration_points")
    return edges if isinstance(edges, list) else []


def _gather_risk_items(data: Dict[str, Any], hld: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Combines high_level_design.risks_and_mitigations with the top-level
    risk_register. The schema describes risk_register as "in addition
    to" the component-level risks, but in practice the same risk (same
    "id") sometimes ends up recorded in both places -- deduped here by
    id (falling back to the full description when no id is present) so
    a single real risk doesn't get reported twice.
    """
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
    """
    Case-insensitive substring match of the component name against each
    risk's free-text fields. Matched risks add probability based on
    their real likelihood/impact enums; unmatched risks contribute
    nothing (never fabricated).
    """
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
    """
    Resolves a dependency/integration-point endpoint string to a known
    component_name, tolerating the naming drift that's common between
    LLM-authored sections of the same document (e.g. "AWS MID Server
    Cluster" referring to "AWS Cloud Discovery & VPC MID Server
    Cluster"). Exact match wins outright. Otherwise, scores every
    component by what fraction of the REFERENCE's own tokens it
    contains (so a short alias fully contained in a longer official
    name scores 1.0), and accepts the best match only if it's a strong,
    unambiguous subset match (>=0.75) AND clearly beats the runner-up
    (by >=0.15) -- a one-to-many reference like "Distributed MID Server
    Clusters (AWS & On-Prem)" that scores similarly against two
    different components is deliberately left unresolved rather than
    guessing which one it means.
    """
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
) -> (Dict[str, Set[str]], Set[str]):
    """
    Builds a reverse-dependency ("if X fails, who is impacted") graph
    from componentSpec.dependencies and integration_points source/target
    pairs. Endpoints are resolved to a known component_name via
    _resolve_component_reference (exact match, then tolerant fuzzy
    match); anything that still can't be confidently resolved is
    recorded in `unresolved` rather than silently dropped or fabricated
    into a new node -- callers surface this so the user knows the graph
    may be incomplete rather than assuming it's exact.
    """
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
            # source calls target; if target fails, source is impacted.
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

    # Deterministic isolated blast radius per component (this component
    # alone fails) -- used to rank single points of failure independent
    # of the Monte Carlo draw.
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
    try:
        import os
        os.makedirs("output", exist_ok=True)
        with open(DESIGN_SIM_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        logger.debug(f"Design simulation metrics saved to {DESIGN_SIM_RESULTS_PATH}")
    except Exception:
        logger.exception("Failed to persist design simulation metrics.")


# ============================================================
# SCALABILITY ANALYSIS
# ============================================================
# Grounded in high_level_design.scalability_and_performance (expected_load,
# scaling_strategy, performance_targets) plus a structural signal the
# resilience graph already gives us for free: fan-in (how many other
# components depend on this one) is exactly what "load concentration"
# means architecturally. A high fan-in component with no declared
# scaling strategy and no elastic-sounding tech in its own stack is a
# real, defensible bottleneck candidate -- not a numeric load prediction
# (the schema has no traffic/throughput figures to simulate), but an
# honest structural flag.

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
# Grounded in high_level_design.security_architecture (a coverage check
# -- which controls are documented at all) and the REAL compliance_status
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
# (the only place the schema records a latency-style metric/target, e.g.
# "P95 latency" / "<200ms") plus the dependency graph's longest chain --
# the schema has no per-hop latency figure, so a long undeclared chain is
# reported as a latency-BUDGET-RISK flag, not a fabricated number.

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
    """
    Resolves the design document to simulate, without depending on the
    LLM faithfully retyping the entire document as a function-call
    argument. A real HLD/LLD/Combined document easily runs to tens of
    thousands of characters, and asking a model to reproduce that
    verbatim in a tool call is exactly the kind of thing that silently
    truncates mid-document (unbalanced braces, a cut-off string) --
    which is what actually happened in practice: the argument arrived
    broken, and this function used to hard-fail on it, mimicking a "no
    dependency data" error that had nothing to do with the document
    itself.

    Precedence:
      1. Already a non-empty dict (a well-behaved caller passed one) -> used as-is.
      2. A non-empty string that parses as valid JSON -> used.
      3. Anything else (missing, empty, or broken/truncated JSON) -> loaded
         fresh from disk via load_master_design_json(), the same file
         Step 1 of the query agent's flow already reads. This is the
         expected path for the LLM tool call: it does not need to pass
         the document at all.
    """
    if isinstance(design_json_str, dict) and design_json_str:
        return design_json_str

    if design_json_str:
        try:
            return _extract_valid_json(str(design_json_str).strip())
        except Exception:
            logger.warning(
                "simulate_design_* received an unparseable design_json_str argument "
                "(likely truncated by the model) -- falling back to loading "
                "output/design_data.json directly from disk instead."
            )

    data = load_master_design_json()
    if not data:
        raise ValueError(
            "No design document data available -- neither a usable argument was "
            "provided nor is output/design_data.json present on disk."
        )
    return data


# ============================================================
# TOOL 1: RESILIENCE-ONLY SIMULATION (standalone, narrower)
# ============================================================

def simulate_design_resilience(design_json_str=None) -> str:
    """Resilience/blast-radius dimension only. Kept as a standalone tool
    for callers that only want that one dimension; the composite
    simulate_design_architecture (below) is what the query agent uses.
    The argument is optional -- see _resolve_input_data."""
    try:
        data = _resolve_input_data(design_json_str)
        metrics = _run_core_design_simulation(data, iterations=2000)
        _persist_design_simulation_metrics(metrics)
        return json.dumps(metrics)

    except Exception as e:
        logger.exception("Design resilience simulation failed.")
        return json.dumps({
            "error": "design_simulation_failed",
            "detail": str(e),
        })


# ============================================================
# TOOL 1b: COMPOSITE SIMULATION (resilience + scalability + security + latency)
# ============================================================

def simulate_design_architecture(design_json_str=None) -> str:
    """
    Runs all four dimensions against the same design document in one
    call: resilience (Monte Carlo blast radius), scalability (structural
    bottleneck + declared-strategy check), security (control coverage +
    real compliance_status enums), and latency (declared performance
    targets + longest undeclared dependency chain). This is the tool the
    query agent uses. The argument is optional -- see _resolve_input_data;
    the normal path is to call this with no argument at all, since the
    tool loads the current design document itself.
    """
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
        logger.exception("Design architecture simulation failed.")
        return json.dumps({
            "error": "design_simulation_failed",
            "detail": str(e),
        })


# ============================================================
# TOOL 2: SENSITIVITY ANALYSIS (WHICH COMPONENT MOST NEEDS REDUNDANCY)
# ============================================================

def perform_design_sensitivity_analysis(design_json_str=None) -> str:
    """
    For each component, re-runs the simulation with that component's
    failure probability driven near zero (i.e. "what if this component
    were made fully redundant"), and ranks components by how much that
    reduces the average blast radius -- the design-side equivalent of
    perform_sensitivity_analysis's "reduce this step's duration by 10%"
    leverage ranking. The argument is optional -- see _resolve_input_data.
    """
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
        logger.exception("Design sensitivity analysis failed.")
        return json.dumps({"error": str(e)})


# ============================================================
# LLM AGENT: DESIGN ARCHITECTURE SIMULATION GATE (PIPELINE-INTERNAL)
# ============================================================
# Design-side analogue of simulation_agent.py's Simulation_Optimization_Agent
# ("REVISION REQUIRED" / "SIMULATION_ALL_APPROVED"). This is the agent that
# gets wired directly into Full_Design_Doc_Pipeline / Update_Design_Doc_Pipeline
# as a self-auditing gate -- distinct from design_simulation_query_agent below,
# which is the standalone, user-facing narrative agent invoked on demand.
# Reuses the SAME "SIMULATION_ALL_APPROVED" marker / simulation_status key
# that simulation_agent.py's gate uses (save_iteration_feedback's
# approval_markers dict already maps it), since the process and design
# pipelines never run concurrently and output/approval.json is reset at the
# start of each pipeline run -- no changes to utils.py/utils_agent.py were
# needed to wire this in.
from ..common.agent_wrappers import ProcessLlmAgent

design_simulation_agent = ProcessLlmAgent(
    name="Design_Architecture_Simulation_Agent",
    description=(
        "Runs the composite resilience/scalability/security/latency simulation against the design document "
        "being built and decides whether the design requires revision before it can proceed."
    ),
    tools=[
        load_master_design_json,
        simulate_design_architecture,
        save_iteration_feedback,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
    instruction_file="design/design_simulation_agent.txt",
)

design_simulation_query_agent = ProcessLlmAgent(
    name="Design_Architecture_Simulation_Query_Agent",
    description=(
        "Runs a composite simulation/analysis over an EXISTING architectural design document covering "
        "resilience (blast-radius Monte Carlo), scalability (structural bottlenecks), security (control "
        "coverage and compliance status), and latency (declared performance targets and dependency chain "
        "depth), in response to queries."
    ),
    tools=[
        load_master_design_json,
        simulate_design_architecture,
        perform_design_sensitivity_analysis,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
    instruction_file="design/design_simulation_query_agent.txt",
)
