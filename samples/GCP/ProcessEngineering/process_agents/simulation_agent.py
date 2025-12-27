import logging
import json
import random
from statistics import mean, pstdev
from typing import Dict, Any

from google.adk.agents import LlmAgent

logger = logging.getLogger("ProcessArchitect.Simulation")

SIM_RESULTS_PATH = "output/simulation_results.json"


# ============================================================
# CORE DISCRETE-EVENT MONTE CARLO SIMULATION
# ============================================================

def _run_core_simulation(data: Dict[str, Any], iterations: int = 2000) -> Dict[str, Any]:
    """
    Internal: runs the discrete-event Monte Carlo simulation
    on a normalized process JSON dict and returns a metrics dict.
    """
    steps = data.get("process_steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError('No valid "process_steps" array found.')

    # -----------------------------------------------
    # STEP METADATA EXTRACTION
    # -----------------------------------------------
    step_info = []
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

        deps = step.get("dependencies") or []
        if isinstance(deps, str):
            deps = [deps]
        if not isinstance(deps, list):
            deps = []

        step_info.append({
            "name": name,
            "base": base_val,
            "deps": [str(d).strip() for d in deps if str(d).strip()]
        })

    if not step_info:
        raise ValueError("No valid steps could be extracted for simulation.")

    # -----------------------------------------------
    # MONTE CARLO DISCRETE-EVENT SIMULATION
    # -----------------------------------------------
    cycle_times = []
    per_step_times = {s["name"]: [] for s in step_info}

    for _ in range(iterations):
        completed = {}  # completed[name] = finish_time

        for s in step_info:
            dep_finish = 0.0
            if s["deps"]:
                dep_finish = max([completed.get(dep, 0.0) for dep in s["deps"]] or [0.0])

            # triangular distribution: low, high, mode = base
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
        "bottlenecks": bottlenecks,
        "resource_contention_risk": contention_risk,
        "per_step_avg": per_step_avg,
    }


def _persist_simulation_metrics(metrics: Dict[str, Any]) -> None:
    """
    Internal: persist metrics (and optionally recommendations later)
    to output/simulation_results.json
    """
    try:
        import os
        os.makedirs("output", exist_ok=True)
        with open(SIM_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        logger.info(f"Simulation metrics saved to {SIM_RESULTS_PATH}")
    except Exception:
        logger.exception("Failed to persist simulation metrics.")


# ============================================================
# TOOL 1: BASELINE PROCESS SIMULATION
# ============================================================
def simulate_process_performance(process_json_str) -> str:
    """
    Accepts:
    - a JSON string
    - a Python dict
    - a message containing JSON after a prefix (e.g. 'COMPLIANCE APPROVED\n{...}')
    """
    try:
        # If already a dict, use it directly
        if isinstance(process_json_str, dict):
            data = process_json_str

        else:
            raw = str(process_json_str).strip()

            # Find the first '{'
            brace_index = raw.find("{")
            if brace_index == -1:
                raise ValueError("No JSON object found in input")

            json_str = raw[brace_index:]

            data = json.loads(json_str)

        metrics = _run_core_simulation(data, iterations=2000)
        _persist_simulation_metrics(metrics)
        return json.dumps(metrics)

    except Exception as e:
        logger.exception("Simulation failed.")
        return f"SIMULATION_ERROR: Unable to parse JSON. Error: {str(e)}"

# ============================================================
# TOOL 2: SCENARIO SIMULATION
# ============================================================

def simulate_scenario(process_json_str: str, scenario_json_str: str) -> str:
    """
    Applies a scenario to the process JSON, runs the same simulation,
    and returns metrics as JSON.

    scenario_json_str example:
    {
      "override_durations": {"Development & Testing": 3.5},
      "remove_dependencies": {"Deployment": ["Sprint Review (Demo)"]},
      "parallelize": ["Development & Testing"]
    }
    """
    try:
        data = json.loads(process_json_str)
        scenario = json.loads(scenario_json_str)

        steps = data.get("process_steps", [])

        # Duration overrides
        overrides = scenario.get("override_durations", {})
        for step in steps:
            name = step.get("step_name")
            if name in overrides:
                step["estimated_duration"] = str(overrides[name])

        # Remove dependencies
        dep_removals = scenario.get("remove_dependencies", {})
        for step in steps:
            name = step.get("step_name")
            if not name:
                continue
            to_remove = dep_removals.get(name, [])
            if to_remove:
                deps = step.get("dependencies") or []
                if isinstance(deps, str):
                    deps = [deps]
                if isinstance(deps, list):
                    step["dependencies"] = [
                        d for d in deps if d not in to_remove
                    ]

        # Parallelization hint: reduce durations by 30%
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
        # Do NOT overwrite the baseline metrics file here
        return json.dumps(metrics)

    except Exception as e:
        logger.exception("Scenario simulation failed.")
        return f"SCENARIO_ERROR: {str(e)}"


# ============================================================
# LLM AGENT: LEAN SIX SIGMA SIMULATION EXPERT
# ============================================================

simulation_agent = LlmAgent(
    name="Simulation_Optimization_Agent",
    model="gemini-2.0-flash-001",
    description="Runs discrete-event simulations to identify bottlenecks and optimization opportunities.",
    tools=[simulate_process_performance],
    instruction=(
        "You are a Lean Six Sigma Simulation Expert.\n\n"
        "INPUT:\n"
        "- You receive a COMPLETE, normalized process JSON from the previous agent.\n"
        "- It includes at least 'process_steps' with 'step_name', 'estimated_duration', "
        "  and optional 'dependencies'.\n\n"
        "MANDATORY TOOL USE:\n"
        "1) You MUST call 'simulate_process_performance' exactly once.\n"
        "   - Pass the FULL process JSON as a string.\n"
        "   - Wait for the tool result.\n\n"
        "SIMULATION RESULT INTERPRETATION:\n"
        "- The tool returns either a JSON string with metrics or a string starting with 'SIMULATION_ERROR'.\n"
        "- If you receive 'SIMULATION_ERROR':\n"
        "    * Output EXACTLY:\n"
        "        OPTIMIZATION REQUIRED\n"
        "        [{\"error_type\": \"simulation_error\", \"detail\": \"<the error message>\"}]\n\n"
        "- If you receive a valid JSON metrics object, parse it and inspect:\n"
        "    * avg_cycle_time\n"
        "    * cycle_time_variance\n"
        "    * bottlenecks (list of step names)\n"
        "    * resource_contention_risk (Low/Medium/High)\n"
        "    * per_step_avg (map of step -> average duration)\n\n"
        "DECISION LOGIC:\n"
        "You MUST choose ONE of two response types:\n\n"
        "A) If ANY of the following are true:\n"
        "   - 'resource_contention_risk' is 'Medium' or 'High', OR\n"
        "   - 'bottlenecks' is non-empty, OR\n"
        "   - 'cycle_time_variance' is more than 25% of 'avg_cycle_time',\n"
        "   THEN you MUST output EXACTLY:\n"
        "       OPTIMIZATION REQUIRED\n"
        "       [\n"
        "         {\"step_name\": \"...\", \"issue\": \"bottleneck\", \"instruction\": \"...\"},\n"
        "         {\"step_name\": \"...\", \"issue\": \"variance\", \"instruction\": \"...\"},\n"
        "         ...\n"
        "       ]\n\n"
        "B) If NONE of the above conditions are true (process is stable and efficient):\n"
        "   THEN you MUST output EXACTLY:\n"
        "       PERFORMANCE APPROVED\n"
        "       {<FULL JSON OBJECT OF THE ORIGINAL PROCESS>}\n\n"
        "STRUCTURE RULES (CRITICAL):\n"
        "- Your response MUST consist of exactly TWO parts:\n"
        "    1) A single line: either 'OPTIMIZATION REQUIRED' or 'PERFORMANCE APPROVED'.\n"
        "    2) Immediately after that line, ONE and only ONE JSON structure:\n"
        "       - A JSON ARRAY of recommendation objects (if optimization is required), OR\n"
        "       - A FULL JSON OBJECT of the process (if performance is approved).\n"
        "- Do NOT output any other text, commentary, or markdown.\n"
        "- Do NOT wrap JSON in ``` fences.\n"
        "- Do NOT output tool calls.\n"
        "- Do NOT truncate the JSON.\n"
    ),
)


# ============================================================
# OPTIONAL: SCENARIO TESTING AGENT (MANUAL USE)
# ============================================================

scenario_testing_agent = LlmAgent(
    name="Scenario_Testing_Agent",
    model="gemini-2.0-flash-001",
    description="Converts what-if scenarios into structured simulation runs.",
    tools=[simulate_scenario],
    instruction=(
        "You are a Process Scenario Analyst.\n\n"
        "INPUT:\n"
        "- The user will describe a 'what-if' scenario, such as:\n"
        "   * Reduce sprint planning duration by 50%.\n"
        "   * Remove a dependency between two steps.\n"
        "   * Parallelize Development & Testing and Code Review.\n\n"
        "YOUR TASK:\n"
        "1) Convert the scenario into a JSON object with keys like:\n"
        "   {\n"
        "     \"override_durations\": {\"Step Name\": 3.5},\n"
        "     \"remove_dependencies\": {\"Step Name\": [\"Other Step\"]},\n"
        "     \"parallelize\": [\"Step Name\"]\n"
        "   }\n"
        "2) CALL 'simulate_scenario' with:\n"
        "   - The FULL process JSON as a string.\n"
        "   - The scenario JSON as a string.\n"
        "3) Output ONLY the metrics JSON returned by 'simulate_scenario'.\n"
        "4) Do NOT output commentary, markdown, or prose.\n"
    ),
)
