"""ITSM structural risk/coverage analysis -- deliberately NOT a Monte
Carlo cycle-time simulation the way process_toolkit's sibling process
simulation is (coded_tools/process/simulation.py, port-duplicated, not
shared here): itsm_json.py's own process_steps schema has no
estimated_duration/dependencies fields at all, by design (the same
"enforced by absence" anti-fabrication discipline the rest of this
schema already uses) -- there is nothing real to feed a timing model.

Instead, this derives genuine risk/coverage signals purely from the
ALREADY-STRUCTURED fields the ITSM JSON baseline actually has: role
concentration (bottleneck risk), missing escalation paths for defined
priorities, missing SLA measurement fields, CIs with an outsized blast
radius (many dependents), and process areas with no RACI governance
entry at all. Every finding names the real field/id it's grounded in --
never a fabricated number.
"""

from collections import Counter
from typing import Any, Dict, List, Optional

from process_toolkit.schema.itsm_json import load_master_itsm_json

# A CI referenced as the target of more than this many relationships is
# flagged as having an outsized blast radius -- a structural signal (how
# much of the environment depends on it), not a fabricated risk score.
_HIGH_BLAST_RADIUS_THRESHOLD = 3

_PROCESS_AREA_SECTIONS = (
    ("incident_management", "Incident Management"),
    ("problem_management", "Problem Management"),
    ("change_management", "Change Management"),
    ("request_fulfillment", "Request Fulfillment"),
    ("service_level_management", "Service Level Management"),
)


def _role_concentration_bottlenecks(data: Dict[str, Any]) -> List[str]:
    """Flags a process area where every single step is owned by the same
    role -- a real single-point-of-failure signal (no handoff, no
    coverage if that role is unavailable), grounded in the steps actually
    present."""
    bottlenecks = []
    for key, label in _PROCESS_AREA_SECTIONS[:4]:
        section = data.get(key)
        if not isinstance(section, dict):
            continue
        steps = [s for s in (section.get("process_steps") or []) if isinstance(s, dict)]
        roles = [s.get("responsible_role") for s in steps if s.get("responsible_role")]
        if len(steps) >= 2 and len(set(roles)) == 1 and len(roles) == len(steps):
            bottlenecks.append(
                f"{label}: all {len(steps)} process steps are owned by the same role "
                f"('{roles[0]}') -- no handoff or coverage if that role is unavailable."
            )
    return bottlenecks


def _escalation_coverage_gaps(data: Dict[str, Any]) -> List[str]:
    """Flags a defined incident priority with no escalation path
    originating from it -- a real coverage gap, grounded in the
    priority_matrix/escalation_paths actually present."""
    incident_management = data.get("incident_management")
    if not isinstance(incident_management, dict):
        return []
    priorities = {
        p.get("priority") for p in (incident_management.get("priority_matrix") or [])
        if isinstance(p, dict) and p.get("priority")
    }
    if not priorities:
        return []
    covered_tiers = {
        e.get("from_tier") for e in (incident_management.get("escalation_paths") or [])
        if isinstance(e, dict) and e.get("from_tier")
    }
    # Priorities are things like "P1"/"P2"; escalation paths are tiered
    # ("Tier 1"/"Tier 2") -- there is no priority->tier that would always
    # match textually, so this only flags the specific, unambiguous case
    # of priorities defined with ZERO escalation paths defined at all.
    if priorities and not covered_tiers:
        return [
            f"{len(priorities)} incident priority level(s) defined ({', '.join(sorted(priorities))}) "
            "but no escalation paths are defined at all."
        ]
    return []


def _missing_sla_measurement_fields(data: Dict[str, Any]) -> List[str]:
    """Flags an SLA entry missing its own measurement_window -- a real
    gap in how the target would actually be tracked, grounded in the
    SLA's own id."""
    slm = data.get("service_level_management")
    if not isinstance(slm, dict):
        return []
    gaps = []
    for sla in (slm.get("slas") or []):
        if isinstance(sla, dict) and sla.get("id") and not str(sla.get("measurement_window") or "").strip():
            gaps.append(f"SLA '{sla['id']}' has a target but no measurement_window defined.")
    return gaps


def _high_blast_radius_cis(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """CIs named as the target_ci of more relationships than the
    threshold -- a real structural fan-in signal from the relationships
    actually declared, not a fabricated risk score."""
    cm = data.get("configuration_management")
    if not isinstance(cm, dict):
        return []
    targets = Counter(
        r.get("target_ci") for r in (cm.get("relationships") or [])
        if isinstance(r, dict) and r.get("target_ci")
    )
    return [
        {"ci": ci, "dependent_count": count}
        for ci, count in sorted(targets.items(), key=lambda kv: -kv[1])
        if count > _HIGH_BLAST_RADIUS_THRESHOLD
    ]


def _raci_coverage_gaps(data: Dict[str, Any]) -> List[str]:
    """Flags a process area that has real content (process steps, SLAs)
    but zero RACI entries naming it -- a real governance gap, grounded in
    which process areas actually have content vs. which the RACI matrix
    actually names."""
    raci_areas = {
        str(r.get("process_area")).strip().lower() for r in (data.get("raci_matrix") or [])
        if isinstance(r, dict) and r.get("process_area")
    }
    gaps = []
    for key, label in _PROCESS_AREA_SECTIONS:
        section = data.get(key)
        if not isinstance(section, dict) or not section:
            continue
        has_content = any(
            isinstance(v, list) and any(isinstance(item, dict) and item for item in v)
            for v in section.values()
        )
        if has_content and label.lower() not in raci_areas:
            gaps.append(f"'{label}' has defined content but no RACI Matrix entry names it as the process area.")
    return gaps


def simulate_itsm_risk_and_coverage(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Loads the current ITSM baseline (unless `data` is passed directly)
    and returns a structural risk/coverage report:
    {"bottlenecks": [...], "escalation_gaps": [...], "sla_measurement_gaps": [...],
     "high_blast_radius_cis": [{"ci", "dependent_count"}, ...], "raci_coverage_gaps": [...]}.
    Every finding is grounded in a real field/id already present in the
    baseline -- nothing here is a fabricated number or guessed severity."""
    resolved = data if isinstance(data, dict) else load_master_itsm_json()
    return {
        "bottlenecks": _role_concentration_bottlenecks(resolved),
        "escalation_gaps": _escalation_coverage_gaps(resolved),
        "sla_measurement_gaps": _missing_sla_measurement_fields(resolved),
        "high_blast_radius_cis": _high_blast_radius_cis(resolved),
        "raci_coverage_gaps": _raci_coverage_gaps(resolved),
    }
