"""PERT-style Monte Carlo process-cycle-time simulation.

Ported near-verbatim from the ADK sample's process/simulation_agent.py
(_run_core_simulation, _detect_cycles, simulate_process_performance,
perform_sensitivity_analysis) -- pure Python, nothing ADK-specific.
"""

import json
import random
from collections import Counter
from statistics import mean, pstdev
from typing import Any, Dict, List

from coded_tools.common.paths import output_path
from coded_tools.common.process_json import extract_valid_json, load_master_process_json

SIM_RESULTS_FILENAME = "simulation_results.json"


def _detect_cycles(step_info: List[Dict[str, Any]]) -> None:
    graph = {s["name"]: s["deps"] for s in step_info}
    visited, stack = set(), set()

    def visit(node):
        if node in stack:
            raise ValueError(f"Circular dependency detected at step: {node}")
        if node in visited:
            return
        stack.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        stack.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _run_core_simulation(data: Dict[str, Any], iterations: int = 2000) -> Dict[str, Any]:
    steps = data.get("process_steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError('No valid "process_steps" array found.')

    step_info = []
    all_units = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = step.get("step_name") or step.get("name") or "Unnamed Task"
        dur_str = step.get("estimated_duration", "1")
        tokens = str(dur_str).split()
        base_val = 1.0
        if tokens:
            try:
                base_val = float(tokens[0].replace(",", "."))
            except Exception:
                base_val = 1.0
            base_val = max(0.1, min(base_val, 1000))
            if len(tokens) > 1:
                all_units.append(tokens[1].lower())
        deps = step.get("dependencies") or []
        if isinstance(deps, str):
            deps = [deps]
        step_info.append({"name": name, "base": base_val, "deps": [str(d).strip() for d in deps if str(d).strip()]})

    _detect_cycles(step_info)

    dominant_unit = Counter(all_units).most_common(1)[0][0] if all_units else "hours"

    cycle_times = []
    per_step_times = {s["name"]: [] for s in step_info}

    for _ in range(iterations):
        completed = {}
        for s in step_info:
            dep_finish = max([completed.get(dep, 0.0) for dep in s["deps"]] or [0.0])
            duration = random.triangular(s["base"] * 0.8, s["base"] * 2.2, s["base"])
            finish_time = dep_finish + duration
            completed[s["name"]] = finish_time
            per_step_times[s["name"]].append(duration)
        cycle_times.append(max(completed.values()))

    avg_cycle = float(mean(cycle_times))
    variance = float(pstdev(cycle_times)) if len(cycle_times) > 1 else 0.0

    bottlenecks = sorted(per_step_times.keys(), key=lambda k: mean(per_step_times[k]), reverse=True)[:3]

    contention_risk = "Low"
    if avg_cycle > 0:
        if variance > avg_cycle * 0.40:
            contention_risk = "High"
        elif variance > avg_cycle * 0.25:
            contention_risk = "Medium"

    return {
        "avg_cycle_time": avg_cycle,
        "cycle_time_variance": variance,
        "time_unit": dominant_unit,
        "bottlenecks": bottlenecks,
        "resource_contention_risk": contention_risk,
        "per_step_avg": {k: float(mean(v)) for k, v in per_step_times.items()},
    }


def _persist_metrics(metrics: Dict[str, Any]) -> None:
    try:
        with open(output_path(SIM_RESULTS_FILENAME), "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def simulate_process_performance(process_json_str: Any = None) -> str:
    try:
        if isinstance(process_json_str, dict):
            data = process_json_str
        elif process_json_str:
            data = extract_valid_json(str(process_json_str))
            if data is None:
                raise ValueError("No valid JSON object found in input.")
        else:
            data = load_master_process_json()

        metrics = _run_core_simulation(data, iterations=2000)
        _persist_metrics(metrics)
        return json.dumps(metrics)
    except Exception as e:
        return json.dumps({"error": "simulation_failed", "detail": str(e)})


def perform_sensitivity_analysis(process_json_str: Any = None) -> str:
    """For each step, re-runs the simulation with that step's duration cut
    by 10%, and ranks steps by how much that reduces average cycle time."""
    try:
        if isinstance(process_json_str, dict):
            data = process_json_str
        elif process_json_str:
            data = extract_valid_json(str(process_json_str))
            if data is None:
                raise ValueError("No valid JSON object found in input.")
        else:
            data = load_master_process_json()

        baseline = _run_core_simulation(data, iterations=500)
        base_time = baseline["avg_cycle_time"]

        steps = data.get("process_steps", [])
        impact_results = []

        for step in steps:
            modified = json.loads(json.dumps(data))
            step_name = step.get("step_name")
            for s in modified["process_steps"]:
                if s.get("step_name") == step_name:
                    raw_dur = str(s.get("estimated_duration", "1")).split()[0]
                    try:
                        val = float(raw_dur.replace(",", "."))
                        s["estimated_duration"] = str(val * 0.9)
                    except Exception:
                        s["estimated_duration"] = "1.0"
            sim = _run_core_simulation(modified, iterations=500)
            impact_results.append({
                "step_name": step_name,
                "improvement_value": base_time - sim["avg_cycle_time"],
                "new_cycle_time": sim["avg_cycle_time"],
            })

        impact_results.sort(key=lambda x: x["improvement_value"], reverse=True)
        top_leverage = impact_results[0] if impact_results else {}

        return json.dumps({
            "baseline_avg": base_time,
            "top_leverage_step": top_leverage.get("step_name"),
            "potential_saving": top_leverage.get("improvement_value"),
            "time_unit": baseline.get("time_unit", "units"),
            "full_analysis": impact_results[:3],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})
