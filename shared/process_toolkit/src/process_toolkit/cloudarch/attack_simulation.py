"""CloudArch diagram attack simulation: adversarial attack-path analysis
(unauthenticated access, lateral movement, privilege escalation, data
exfiltration, credential compromise), derived purely from the diagram's own
vertices/edges and each component's shape/label vocabulary.

Sibling to cloudarch/simulation.py (operational resilience/scalability/
latency), but deliberately NOT built on that module's _build_impacts_graph/
_blast_radius: those encode a DIRECTED "if X fails, who depends on it
breaks" relationship, which is the wrong shape for attack pivoting
(compromising either end of a drawn connection generally lets an attacker
attempt to move along it in either direction), and have no hook to stop
propagation at a control node (a WAF/firewall/segmentation boundary that is
actually doing its job). This module's graph helpers are undirected and
support a `blocking_ids` stop-set instead.
"""

import json
import re
from typing import Any, Dict, List, Set

from process_toolkit.drawio.graph import parse_drawio_graph
from process_toolkit.drawio.persistence import load_drawio_xml
from process_toolkit.paths import output_path

_STOPWORDS = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "via", "at", "by"}

_ENTRY_POINT_SHAPE_KEYWORDS = (
    "api_gateway", "apigateway", "cloudfront", "route53", "route_53", "alb", "elb",
    "load_balancer", "application_load_balancer", "application_gateway", "front_door",
    "internet_gateway", "nat_gateway", "cloud_cdn", "cloud_armor",
)
_ENTRY_POINT_LABEL_KEYWORDS = ("public", "edge", "dmz", "internet-facing", "internet facing")

_CONTROL_SHAPE_KEYWORDS: Dict[str, tuple] = {
    "waf": ("waf", "web_application_firewall", "cloud_armor", "front_door_waf"),
    "firewall_segmentation": (
        "firewall", "nsg", "security_group", "network_firewall", "vpc_endpoint",
        "privatelink", "private_link", "transit_gateway", "subnet",
    ),
    "identity_mfa_sso": (
        "mfa", "sso", "identity_provider", "cognito", "entra", "okta", "iam_identity_center",
    ),
    "encryption_kms": ("kms", "encryption", "encrypted", "cloudhsm", "key_vault"),
    "monitoring_detection": (
        "guardduty", "securityhub", "security_hub", "defender", "cloudtrail", "sentinel", "siem",
    ),
}

_IDENTITY_SHAPE_KEYWORDS = ("iam", "role", "policy", "identity")
_PRIVILEGED_LABEL_KEYWORDS = ("admin", "root", "full-access", "full access", "*")

_DATA_STORE_SHAPE_KEYWORDS = (
    "rds", "dynamodb", "s3", "blob_storage", "cosmos_db", "sql_database",
    "bigquery", "cloud_storage", "redshift", "cloud_sql",
)

_TECHNIQUE_CATEGORIES = (
    "unauthenticated_access", "lateral_movement", "privilege_escalation",
    "data_exfiltration", "credential_compromise",
)


def _tokenize(text: str) -> Set[str]:
    tokens = re.split(r"[^a-z0-9]+", (text or "").lower())
    return {t for t in tokens if t and t not in _STOPWORDS and len(t) > 1}


def _matches_any(vertex: Dict[str, Any], keywords: tuple) -> bool:
    haystack = f"{vertex.get('shape_slug', '')} {vertex.get('value', '')}".lower()
    return any(kw in haystack for kw in keywords)


def _detect_entry_points(vertices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entry_points = []
    for v in vertices:
        if _matches_any(v, _ENTRY_POINT_SHAPE_KEYWORDS) or _matches_any(v, _ENTRY_POINT_LABEL_KEYWORDS):
            entry_points.append(v)
    return entry_points


def _classify_controls(vertices: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    controls: Dict[str, List[Dict[str, Any]]] = {name: [] for name in _CONTROL_SHAPE_KEYWORDS}
    for v in vertices:
        for control_type, keywords in _CONTROL_SHAPE_KEYWORDS.items():
            if _matches_any(v, keywords):
                controls[control_type].append(v)
    return controls


def _detect_data_stores(vertices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [v for v in vertices if _matches_any(v, _DATA_STORE_SHAPE_KEYWORDS)]


def _detect_privileged_identities(vertices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    identities = []
    for v in vertices:
        if _matches_any(v, _IDENTITY_SHAPE_KEYWORDS) or _matches_any(v, _PRIVILEGED_LABEL_KEYWORDS):
            identities.append(v)
    return identities


def _build_adjacency(vertices: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    vertex_ids = {v["id"] for v in vertices}
    adjacency: Dict[str, Set[str]] = {vid: set() for vid in vertex_ids}
    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if src in vertex_ids and tgt in vertex_ids:
            adjacency[src].add(tgt)
            adjacency[tgt].add(src)
    return adjacency


def _reachable_through(
    start_ids: Set[str], adjacency: Dict[str, Set[str]], blocking_ids: Set[str]
) -> Set[str]:
    reached = set(start_ids)
    frontier = list(start_ids)
    while frontier:
        node = frontier.pop()
        if node in blocking_ids and node not in start_ids:
            continue
        for neighbor in adjacency.get(node, ()):
            if neighbor not in reached:
                reached.add(neighbor)
                frontier.append(neighbor)
    return reached


def _severity_from_fraction(fraction: float) -> str:
    if fraction > 0.35:
        return "High"
    if fraction > 0.15:
        return "Medium"
    return "Low"


def _vertex_ref(v: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": v["id"], "value": v.get("value", "")}


def _analyze_unauthenticated_access(
    entry_points: List[Dict[str, Any]], adjacency: Dict[str, Set[str]],
    controls: Dict[str, List[Dict[str, Any]]], by_id: Dict[str, Dict[str, Any]],
    data_store_ids: Set[str], identity_ids: Set[str],
) -> List[Dict[str, Any]]:
    waf_ids = {c["id"] for c in controls["waf"]}
    findings = []
    for entry in entry_points:
        neighbors = adjacency.get(entry["id"], set())
        if entry["id"] in waf_ids or (neighbors & waf_ids):
            continue
        sensitive_neighbor = bool(neighbors & (data_store_ids | identity_ids))
        findings.append({
            "entry_point_id": entry["id"],
            "entry_point_value": entry.get("value", ""),
            "technique_category": "unauthenticated_access",
            "reachable": [_vertex_ref(by_id[n]) for n in neighbors if n in by_id],
            "blocked_by": [],
            "missing_controls": ["waf"],
            "severity": "High" if sensitive_neighbor else "Medium",
        })
    return findings


def _analyze_lateral_movement(
    entry_points: List[Dict[str, Any]], adjacency: Dict[str, Set[str]],
    controls: Dict[str, List[Dict[str, Any]]], by_id: Dict[str, Dict[str, Any]], total: int,
) -> List[Dict[str, Any]]:
    segmentation = controls["firewall_segmentation"]
    segmentation_ids = {c["id"] for c in segmentation}
    findings = []
    for entry in entry_points:
        reachable = _reachable_through({entry["id"]}, adjacency, segmentation_ids) - {entry["id"]}
        if len(reachable) < 2:
            continue
        fraction = len(reachable) / max(1, total)
        if not segmentation:
            severity = "High" if fraction > 0.15 else "Medium"
            missing = ["network_segmentation"]
        else:
            severity = "Medium"
            missing = []
        findings.append({
            "entry_point_id": entry["id"],
            "entry_point_value": entry.get("value", ""),
            "technique_category": "lateral_movement",
            "reachable": [_vertex_ref(by_id[n]) for n in reachable if n in by_id],
            "blocked_by": [_vertex_ref(c) for c in segmentation if c["id"] in reachable],
            "missing_controls": missing,
            "severity": severity,
        })
    return findings


def _analyze_privilege_escalation(
    identities: List[Dict[str, Any]], controls: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if controls["identity_mfa_sso"]:
        return []
    findings = []
    for identity in identities:
        privileged = _matches_any(identity, _PRIVILEGED_LABEL_KEYWORDS)
        findings.append({
            "entry_point_id": identity["id"],
            "entry_point_value": identity.get("value", ""),
            "technique_category": "privilege_escalation",
            "reachable": [],
            "blocked_by": [],
            "missing_controls": ["identity_mfa_sso"],
            "severity": "High" if privileged else "Medium",
        })
    return findings


def _analyze_data_exfiltration(
    entry_points: List[Dict[str, Any]], data_stores: List[Dict[str, Any]],
    adjacency: Dict[str, Set[str]], controls: Dict[str, List[Dict[str, Any]]],
    by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    blocking_ids = {c["id"] for c in controls["waf"]} | {c["id"] for c in controls["firewall_segmentation"]}
    encryption_ids = {c["id"] for c in controls["encryption_kms"]}
    findings = []
    for entry in entry_points:
        reachable = _reachable_through({entry["id"]}, adjacency, blocking_ids)
        for store in data_stores:
            if store["id"] not in reachable:
                continue
            store_neighbors = adjacency.get(store["id"], set())
            encrypted = store["id"] in encryption_ids or bool(store_neighbors & encryption_ids)
            findings.append({
                "entry_point_id": entry["id"],
                "entry_point_value": entry.get("value", ""),
                "technique_category": "data_exfiltration",
                "reachable": [_vertex_ref(store)],
                "blocked_by": [_vertex_ref(by_id[n]) for n in reachable if n in blocking_ids and n in by_id],
                "missing_controls": [] if encrypted else ["encryption_kms"],
                "severity": "Medium" if encrypted else "High",
            })
    return findings


def _analyze_credential_compromise(
    entry_points: List[Dict[str, Any]], identities: List[Dict[str, Any]],
    adjacency: Dict[str, Set[str]], controls: Dict[str, List[Dict[str, Any]]],
    by_id: Dict[str, Dict[str, Any]], total: int,
) -> List[Dict[str, Any]]:
    if controls["identity_mfa_sso"]:
        return []
    findings = []
    for vertex in [*entry_points, *identities]:
        reachable = _reachable_through({vertex["id"]}, adjacency, set()) - {vertex["id"]}
        fraction = len(reachable) / max(1, total)
        findings.append({
            "entry_point_id": vertex["id"],
            "entry_point_value": vertex.get("value", ""),
            "technique_category": "credential_compromise",
            "reachable": [_vertex_ref(by_id[n]) for n in reachable if n in by_id],
            "blocked_by": [],
            "missing_controls": ["identity_mfa_sso"],
            "severity": _severity_from_fraction(fraction),
        })
    return findings


def _summarize(attack_paths: List[Dict[str, Any]]) -> Dict[str, Any]:
    _SEVERITY_RANK = {"Low": 0, "Medium": 1, "High": 2}
    summaries: Dict[str, Any] = {}
    for category in _TECHNIQUE_CATEGORIES:
        matching = [p for p in attack_paths if p["technique_category"] == category]
        worst = max((p["severity"] for p in matching), key=lambda s: _SEVERITY_RANK[s], default="Low")
        summaries[category] = {"flagged": bool(matching), "count": len(matching), "severity": worst}
    return summaries


def _persist_attack_results(results: Dict[str, Any]) -> None:
    try:
        with open(output_path("cloudarch_attack_simulation_results.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def simulate_cloudarch_attack(xml_content: Any = None) -> str:
    try:
        if not xml_content:
            loaded = load_drawio_xml()
            if loaded.get("status") != "OK" or not loaded.get("xml"):
                return json.dumps({"error": "no_diagram_available", "detail": "No cloud architecture diagram has been saved yet."})
            xml_content = loaded["xml"]

        graph = parse_drawio_graph(xml_content)
        vertices, edges = graph["vertices"], graph["edges"]
        if not vertices:
            raise ValueError(
                "No simulatable service nodes found in the diagram (vertices with a "
                "shape=mxgraph.<provider>.<name> icon token). Generate a diagram first."
            )

        by_id = {v["id"]: v for v in vertices}
        total = len(vertices)
        adjacency = _build_adjacency(vertices, edges)
        entry_points = _detect_entry_points(vertices)
        controls = _classify_controls(vertices)
        data_stores = _detect_data_stores(vertices)
        identities = _detect_privileged_identities(vertices)
        data_store_ids = {v["id"] for v in data_stores}
        identity_ids = {v["id"] for v in identities}

        attack_paths: List[Dict[str, Any]] = []
        attack_paths += _analyze_unauthenticated_access(
            entry_points, adjacency, controls, by_id, data_store_ids, identity_ids
        )
        attack_paths += _analyze_lateral_movement(entry_points, adjacency, controls, by_id, total)
        attack_paths += _analyze_privilege_escalation(identities, controls)
        attack_paths += _analyze_data_exfiltration(entry_points, data_stores, adjacency, controls, by_id)
        attack_paths += _analyze_credential_compromise(entry_points, identities, adjacency, controls, by_id, total)

        technique_summaries = _summarize(attack_paths)
        severities = [s["severity"] for s in technique_summaries.values() if s["flagged"]]
        overall_risk_rating = "High" if "High" in severities else ("Medium" if "Medium" in severities else "Low")

        result = {
            "entry_points": [_vertex_ref(e) for e in entry_points],
            "attack_paths": attack_paths,
            "technique_summaries": technique_summaries,
            "overall_risk_rating": overall_risk_rating,
        }
        _persist_attack_results(result)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": "cloudarch_attack_simulation_failed", "detail": str(e)})
