# process_agents/simulation_agent.py

import logging
import json
import random
import re
from statistics import mean, pstdev
from typing import Dict, Any

from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .utils import (
    load_instruction,
    load_master_process_json,
    save_iteration_feedback
)

import time
import random

logger = logging.getLogger("ProcessArchitect.Simulation")

SIM_RESULTS_PATH = "output/simulation_results.json"
PROCESS_JSON = "output/process_data.json"

# ============================================================
# JSON EXTRACTION + REPAIR + VALIDATION
# ============================================================

def _attempt_json_repair(raw: str) -> str:
    """
    Lightweight JSON repair:
    - removes trailing commas
    - fixes ',]' and ',}'
    - strips BOM or weird whitespace
    """
    cleaned = raw.strip()

    # Remove trailing commas before ] or }
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)

    # Remove BOM if present
    cleaned = cleaned.replace("\ufeff", "")

    return cleaned


def _extract_valid_json(raw: str):
    """
    Extracts the largest valid JSON object from an LLM response.
    Handles:
    - trailing commentary
    - leading text
    - nested braces
    - multiple JSON blocks
    - malformed endings

    Returns:
        dict if valid JSON found
        raises ValueError otherwise
    """
    raw = raw.strip()
    logger.debug(f"Raw LLM output received for simulation (first 5000 chars): {raw[:5000]}")

    stack = []
    start_idx = None
    candidates = []

    # Greedy brace matcher
    for i, ch in enumerate(raw):
        if ch == "{":
            if not stack:
                start_idx = i
            stack.append("{")
        elif ch == "}":
            if stack:
                stack.pop()
                if not stack and start_idx is not None:
                    candidates.append(raw[start_idx:i+1])
                    start_idx = None

    # Try each candidate from longest to shortest
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


def _validate_process_json(data: Dict[str, Any]):
    """
    Ensures the extracted JSON has the required structure.
    Auto-repairs common LLM drift cases:
    - process_steps is a dict instead of a list
    - process_steps is a JSON string
    - process_steps is None
    """

    if "process_steps" not in data:
        raise ValueError("JSON missing required key: process_steps")

    steps = data["process_steps"]

    # --- Auto-repair: process_steps is a JSON string ---
    if isinstance(steps, str):
        try:
            parsed = json.loads(steps)
            steps = parsed
            data["process_steps"] = parsed
        except Exception:
            raise ValueError("process_steps is a string but not valid JSON")

    # --- Auto-repair: process_steps is a dict ---
    if isinstance(steps, dict):
        # Convert dict → list of step objects
        repaired = list(steps.values())
        data["process_steps"] = repaired
        steps = repaired

    # --- Auto-repair: process_steps is None ---
    if steps is None:
        raise ValueError("process_steps is null — cannot repair automatically")

    # --- Final strict validation ---
    if not isinstance(steps, list):
        raise ValueError("process_steps must be a list after repair")

    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Each process step must be an object")
        if "step_name" not in step:
            raise ValueError("Each step must contain step_name")


def _detect_cycles(step_info):
    """
    Detects circular dependencies in the process graph.
    """
    graph = {s["name"]: s["deps"] for s in step_info}

    visited = set()
    stack = set()

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


# ============================================================
# CORE DISCRETE-EVENT MONTE CARLO SIMULATION
# ============================================================

def _run_core_simulation(data: Dict[str, Any], iterations: int = 2000) -> Dict[str, Any]:
    from collections import Counter
    
    steps = data.get("process_steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError('No valid "process_steps" array found.')

    step_info = []
    all_units = []

    # Extract step metadata
    for step in steps:
        if not isinstance(step, dict):
            continue

        name = step.get("step_name") or step.get("name") or "Unnamed Task"

        # Parse duration
        dur_str = step.get("estimated_duration", "1")
        tokens = str(dur_str).split()
        base_val = 1.0

        if tokens:
            try:
                base_val = float(tokens[0].replace(",", "."))
            except Exception:
                base_val = 1.0

            # Clamp insane durations
            base_val = max(0.1, min(base_val, 1000))

            if len(tokens) > 1:
                all_units.append(tokens[1].lower())

        deps = step.get("dependencies") or []
        if isinstance(deps, str):
            deps = [deps]

        step_info.append({
            "name": name,
            "base": base_val,
            "deps": [str(d).strip() for d in deps if str(d).strip()]
        })

    # Detect circular dependencies
    _detect_cycles(step_info)

    dominant_unit = Counter(all_units).most_common(1)[0][0] if all_units else "hours"

    cycle_times = []
    per_step_times = {s["name"]: [] for s in step_info}

    # Monte Carlo simulation
    for _ in range(iterations):
        completed = {}
        for s in step_info:
            dep_finish = max([completed.get(dep, 0.0) for dep in s["deps"]] or [0.0])

            low = s["base"] * 0.8
            high = s["base"] * 2.2
            mode = s["base"]
            duration = random.triangular(low, high, mode)

            finish_time = dep_finish + duration
            completed[s["name"]] = finish_time
            per_step_times[s["name"]].append(duration)

        cycle_times.append(max(completed.values()))

    avg_cycle = float(mean(cycle_times))
    variance = float(pstdev(cycle_times)) if len(cycle_times) > 1 else 0.0

    bottlenecks = sorted(
        per_step_times.keys(),
        key=lambda k: mean(per_step_times[k]),
        reverse=True
    )[:3]

    contention_risk = "Low"
    if avg_cycle > 0:
        if variance > avg_cycle * 0.40:
            contention_risk = "High"
        elif variance > avg_cycle * 0.25:
            contention_risk = "Medium"

    per_step_avg = {k: float(mean(v)) for k, v in per_step_times.items()}

    return {
        "avg_cycle_time": avg_cycle,
        "cycle_time_variance": variance,
        "time_unit": dominant_unit,
        "bottlenecks": bottlenecks,
        "resource_contention_risk": contention_risk,
        "per_step_avg": per_step_avg
    }


def _persist_simulation_metrics(metrics: Dict[str, Any]) -> None:
    try:
        import os
        os.makedirs("output", exist_ok=True)
        with open(SIM_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        logger.info(f"Simulation metrics saved to {SIM_RESULTS_PATH}")
    except Exception:
        logger.exception("Failed to persist simulation metrics.")


def _persist_process_data(data: Dict[str, Any]) -> None:
    try:
        import os
        os.makedirs("output", exist_ok=True)
        with open(PROCESS_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Process data saved to {PROCESS_JSON}")
    except Exception:
        logger.exception("Failed to persist process data.")

# ============================================================
# TOOL 1: BASELINE PROCESS SIMULATION
# ============================================================

def simulate_process_performance(process_json_str) -> str:
    try:
        if isinstance(process_json_str, dict):
            data = process_json_str
        else:
            raw = str(process_json_str).strip()
            data = _extract_valid_json(raw)

        _validate_process_json(data)

        metrics = _run_core_simulation(data, iterations=2000)
        _persist_simulation_metrics(metrics)
        return json.dumps(metrics)

    except Exception as e:
        logger.exception("Simulation failed.")
        return json.dumps({
            "error": "simulation_failed",
            "detail": str(e)
        })


# ============================================================
# TOOL 2: SCENARIO SIMULATION
# ============================================================

def simulate_scenario(process_json_str: str, scenario_json_str: str) -> str:
    """
    Simulates a process scenario by applying overrides and running the core simulation.
    """
    time.sleep(1.75 + random.random() * 0.75)
    try:
        data = json.loads(process_json_str)
        scenario = json.loads(scenario_json_str)

        steps = data.get("process_steps", [])

        overrides = scenario.get("override_durations", {})
        for step in steps:
            name = step.get("step_name")
            if name in overrides:
                step["estimated_duration"] = str(overrides[name])

        dep_removals = scenario.get("remove_dependencies", {})
        for step in steps:
            name = step.get("step_name")
            to_remove = dep_removals.get(name, [])
            if to_remove:
                deps = step.get("dependencies") or []
                if isinstance(deps, str):
                    deps = [deps]
                step["dependencies"] = [d for d in deps if d not in to_remove]

        parallel = scenario.get("parallelize", [])
        for step in steps:
            name = step.get("step_name")
            if name in parallel:
                dur = step.get("estimated_duration", "1")
                tokens = str(dur).split()
                base = 1.0
                if tokens:
                    try:
                        base = float(tokens[0].replace(",", "."))
                    except Exception:
                        base = 1.0
                step["estimated_duration"] = str(base * 0.7)

        metrics = _run_core_simulation(data, iterations=2000)
        return json.dumps(metrics)

    except Exception as e:
        logger.exception("Scenario simulation failed.")
        return json.dumps({
            "error": "scenario_simulation_failed",
            "detail": str(e)
        })


# ============================================================
# LLM AGENT: LEAN SIX SIGMA SIMULATION EXPERT
# ============================================================

simulation_agent = LlmAgent(
    name="Simulation_Optimization_Agent",
    model="gemini-2.0-flash-001",
    description="Runs discrete-event simulations to identify bottlenecks and optimization opportunities.",
    tools=[
        load_master_process_json,
        save_iteration_feedback,
        simulate_process_performance
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
    instruction=load_instruction("simulation_agent.txt"),
)

simulation_query_agent = LlmAgent(
    name="Simulation_Optimization_Query_Agent",
    model="gemini-2.0-flash-001",
    description="Runs discrete-event simulations to identify bottlenecks and optimization opportunities in response to queries.",
    tools=[
        load_master_process_json,
        simulate_process_performance
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.5,
        top_p=1,
    ),
    instruction=load_instruction("simulation_query_agent.txt"),
)