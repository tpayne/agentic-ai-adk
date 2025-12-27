# process_agents/simulation_agent.py

import logging
import json
import random
from statistics import mean, pstdev
from google.adk.agents import LlmAgent

logger = logging.getLogger("ProcessArchitect.Simulation")


# ============================================================
# DISCRETE-EVENT MONTE CARLO SIMULATION TOOL
# ============================================================

def simulate_process_performance(process_json_str: str):
    """
    Runs a discrete-event Monte Carlo simulation over the process
    to identify bottlenecks, variance, and resource contention.

    INPUT:
    - process_json_str: stringified JSON, expected to contain:
        {
          "process_steps": [
             {
               "step_name": "...",
               "estimated_duration": "4 hours",
               "dependencies": [ "Sprint Planning", ... ]
             },
             ...
          ]
        }

    BEHAVIOR:
    - Parses process_steps.
    - Extracts base durations from 'estimated_duration' (first numeric token).
    - Applies a triangular distribution per step to simulate variability.
    - Respects dependencies by ensuring steps start only after predecessors complete.
    - Runs N iterations and computes:
        * avg_cycle_time
        * cycle_time_variance
        * bottlenecks (top 3 slowest steps)
        * resource_contention_risk (Low/Medium/High)
        * per_step_avg (average simulated duration per step)

    OUTPUT:
    - JSON string with the above metrics, OR
    - "SIMULATION_ERROR: <message>" on failure.
    """
    try:
        data = json.loads(process_json_str)
        steps = data.get("process_steps", [])
        if not isinstance(steps, list) or not steps:
            return 'SIMULATION_ERROR: No valid "process_steps" array found.'

        iterations = 2000  # more stable distribution over many runs

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
            return 'SIMULATION_ERROR: No valid steps could be extracted for simulation.'

        # -----------------------------------------------
        # MONTE CARLO DISCRETE-EVENT SIMULATION
        # -----------------------------------------------
        cycle_times = []
        per_step_times = {s["name"]: [] for s in step_info}

        for _ in range(iterations):
            # completed[name] = finish_time for that step
            completed = {}

            # simple pass in defined order; dependencies handled via waiting
            for s in step_info:
                # wait for all dependencies to complete
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

            # cycle time = max finish time across all steps
            cycle_times.append(max(completed.values()))

        # -----------------------------------------------
        # METRIC CALCULATION
        # -----------------------------------------------
        avg_cycle = float(mean(cycle_times))
        variance = float(pstdev(cycle_times)) if len(cycle_times) > 1 else 0.0

        # Top 3 bottlenecks by average step time
        bottlenecks = sorted(
            per_step_times.keys(),
            key=lambda k: mean(per_step_times[k]),
            reverse=True
        )[:3]

        # Simple variance-based contention risk heuristic
        contention_risk = "Low"
        if avg_cycle > 0:
            if variance > avg_cycle * 0.40:
                contention_risk = "High"
            elif variance > avg_cycle * 0.25:
                contention_risk = "Medium"

        per_step_avg = {k: float(mean(v)) for k, v in per_step_times.items()}

        result = {
            "avg_cycle_time": avg_cycle,
            "cycle_time_variance": variance,
            "bottlenecks": bottlenecks,
            "resource_contention_risk": contention_risk,
            "per_step_avg": per_step_avg
        }

        return json.dumps(result)

    except Exception as e:
        logger.exception("Simulation failed.")
        return f"SIMULATION_ERROR: {str(e)}"


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
        "   - The array MUST contain specific, actionable engineering instructions, such as:\n"
        "       * parallelize this step with <other_step>\n"
        "       * reduce approvals or handoffs\n"
        "       * split the step into smaller units\n"
        "       * add resources or automation to this step\n"
        "       * decouple or relax dependencies\n\n"
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
