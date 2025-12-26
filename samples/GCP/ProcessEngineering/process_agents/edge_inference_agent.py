# process_agents/edge_inference_agent.py

from google.adk.agents import LlmAgent
import os
import re
import json
import traceback
import networkx as nx
import matplotlib.pyplot as plt
import logging
from typing import List, Tuple, Any, Dict

logger = logging.getLogger("ProcessArchitect.EdgeInference")


# ============================================================
#  JSON LOADING (GENERIC)
# ============================================================

def _load_process_json(path: str = "output/process_data.json") -> dict | None:
    """
    Load the normalized process JSON from disk.

    Expected canonical high-level schema:

    {
      "process_name": string,
      "version": string,
      "introduction": string,
      "stakeholders": [],
      "process_steps": [],
      "tools_summary": {},
      "metrics": [],
      "reporting_and_analytics": {},
      "system_requirements": [],
      "appendix": {}
    }

    process_steps may contain ANY additional fields.
    """
    try:
        if not os.path.exists(path):
            logger.error(f"Process JSON not found at {path}")
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load process JSON")
        return None


# ============================================================
#  STEP ORDERING (GENERIC)
# ============================================================

def _order_steps(steps: list[dict]) -> list[dict]:
    """
    Generic ordering logic:

    Priority:
    1) step_number (numeric)
    2) step_id (numeric or numeric-string)
    3) step (numeric)              <-- added for schemas like the Scrum example
    4) original list order
    """
    if not steps:
        return []

    # 1) step_number
    if any("step_number" in s for s in steps):
        with_num = [s for s in steps if isinstance(s.get("step_number"), (int, float))]
        without_num = [s for s in steps if not isinstance(s.get("step_number"), (int, float))]
        with_num_sorted = sorted(with_num, key=lambda s: s["step_number"])
        return with_num_sorted + without_num

    # 2) step_id
    def _parse_id(val: Any) -> float:
        try:
            return float(val)
        except Exception:
            return float("inf")

    if any("step_id" in s for s in steps):
        return sorted(steps, key=lambda s: _parse_id(s.get("step_id")))

    # 3) step (e.g. your Simple Scrum Process JSON)
    if any("step" in s for s in steps):
        with_step = [s for s in steps if isinstance(s.get("step"), (int, float))]
        without_step = [s for s in steps if not isinstance(s.get("step"), (int, float))]
        with_step_sorted = sorted(with_step, key=lambda s: s["step"])
        return with_step_sorted + without_step

    # 4) fallback
    return steps


# ============================================================
#  SWIMLANE HELPERS
# ============================================================

def _get_lane(step: dict) -> str:
    """
    Determine swimlane name.

    Priority:
    - step["lane"]
    - step["responsible_party"]
    - step["responsibleRole"]
    - default: "Process"
    """
    lane = (
        step.get("lane")
        or step.get("responsible_party")
        or step.get("responsibleRole")
        or "Process"
    )
    if isinstance(lane, str) and lane.strip():
        return lane.strip()
    return "Process"


def _normalize_node_label(name: str) -> str:
    return name.strip()


# ============================================================
#  DEPENDENCY RESOLUTION (GENERIC)
# ============================================================

def _build_id_index(steps: list[dict]) -> Dict[str, dict]:
    """
    Build a lookup index so dependencies can refer to:
    - step_number
    - step_id
    - step
    - step_name / name
    """
    index: Dict[str, dict] = {}
    for s in steps:
        if not isinstance(s, dict):
            continue

        # step_number
        if "step_number" in s:
            val = s.get("step_number")
            index[f"step_number:{val}"] = s

        # step_id
        if "step_id" in s:
            val = s.get("step_id")
            index[f"step_id:{val}"] = s

        # step
        if "step" in s:
            val = s.get("step")
            index[f"step:{val}"] = s

        # step_name / name
        name = s.get("step_name") or s.get("name")
        if isinstance(name, str) and name.strip():
            index[f"step_name:{name.strip()}"] = s

    return index


def _resolve_dependency(dep: Any, index: Dict[str, dict]) -> dict | None:
    """
    Resolve a dependency token to a step dict.
    """
    keys = [
        f"step_number:{dep}",
        f"step_id:{dep}",
        f"step:{dep}",
    ]

    if isinstance(dep, str) and dep.strip():
        keys.append(f"step_name:{dep.strip()}")

    for k in keys:
        if k in index:
            return index[k]

    return None


# ============================================================
#  EDGE INFERENCE (GENERIC + HARD FALLBACK)
# ============================================================

def _infer_edges_from_json() -> Tuple[str | None, List[Tuple[str, str]], Dict[str, str]]:
    """
    Infer:
    - process_name
    - edges (linear + branching)
    - lane_map (node -> lane)

    ALWAYS returns at least one edge.

    For schemas like your Simple Scrum Process, this will produce a
    meaningful linear flow through the named steps.
    """
    data = _load_process_json()
    if not data or not isinstance(data, dict):
        return "process", [("Start", "End")], {"Start": "Process", "End": "Process"}

    process_name = data.get("process_name") or "process"

    raw_steps = data.get("process_steps") or []
    if not isinstance(raw_steps, list):
        return process_name, [("Start", "End")], {"Start": "Process", "End": "Process"}

    # Collect valid steps
    valid_steps: List[dict] = []
    for s in raw_steps:
        if isinstance(s, dict):
            name = s.get("step_name") or s.get("name")
            if isinstance(name, str) and name.strip():
                valid_steps.append(s)
        elif isinstance(s, str) and s.strip():
            # allow list of bare strings as step names too
            valid_steps.append({"name": s.strip()})

    if not valid_steps:
        return process_name, [("Start", "End")], {"Start": "Process", "End": "Process"}

    ordered_steps = _order_steps(valid_steps)

    # Node labels + lanes
    node_labels: List[str] = []
    lane_map: Dict[str, str] = {}
    for s in ordered_steps:
        raw_name = s.get("step_name") or s.get("name")
        if not isinstance(raw_name, str):
            continue
        label = _normalize_node_label(raw_name)
        if not label:
            continue
        if label not in node_labels:
            node_labels.append(label)
        lane_map[label] = _get_lane(s)

    # Base linear edges
    edges: List[Tuple[str, str]] = []
    if len(node_labels) == 1:
        only = node_labels[0]
        edges = [("Start", only), (only, "End")]
        lane_map["Start"] = "Process"
        lane_map["End"] = "Process"
    else:
        for i in range(len(node_labels) - 1):
            edges.append((node_labels[i], node_labels[i + 1]))

    # Branching edges (if any dependencies exist)
    id_index = _build_id_index(ordered_steps)
    for s in ordered_steps:
        this_name = s.get("step_name") or s.get("name")
        if not isinstance(this_name, str) or not this_name.strip():
            continue
        this_label = _normalize_node_label(this_name)

        deps = s.get("dependencies") or []
        if not isinstance(deps, list):
            continue

        for dep in deps:
            pred = _resolve_dependency(dep, id_index)
            if not pred:
                continue
            pred_name = pred.get("step_name") or pred.get("name")
            if not isinstance(pred_name, str) or not pred_name.strip():
                continue
            pred_label = _normalize_node_label(pred_name)
            if pred_label != this_label:
                edge = (pred_label, this_label)
                if edge not in edges:
                    edges.append(edge)

    # Absolute fallback
    if not edges:
        edges = [("Start", "End")]
        lane_map["Start"] = "Process"
        lane_map["End"] = "Process"

    return process_name, edges, lane_map


# ============================================================
#  LAYOUT (SWIMLANES)
# ============================================================

def _compute_positions(edges: List[Tuple[str, str]], lane_map: Dict[str, str]):
    """
    Swimlane layout:
    - y-axis = lane
    - x-axis = sequence order
    """
    nodes: List[str] = []
    for s, d in edges:
        if s not in nodes:
            nodes.append(s)
        if d not in nodes:
            nodes.append(d)

    lanes = sorted(set(lane_map.get(n, "Process") for n in nodes))
    lane_y = {lane: idx for idx, lane in enumerate(lanes)}

    lane_positions: Dict[str, List[str]] = {lane: [] for lane in lanes}
    for n in nodes:
        lane = lane_map.get(n, "Process")
        if n not in lane_positions[lane]:
            lane_positions[lane].append(n)

    pos: Dict[str, Tuple[float, float]] = {}
    for lane, items in lane_positions.items():
        y = float(lane_y[lane])
        for i, n in enumerate(items):
            pos[n] = (float(i), y)

    return pos


# ============================================================
#  DIAGRAM GENERATION (ALWAYS PRODUCES SOMETHING)
# ============================================================

def generate_clean_diagram(process_name: str, edge_list_json: str) -> str:
    """
    Generates a BPMN-style swimlane diagram.

    ALWAYS produces a diagram, even if:
    - JSON missing
    - process_steps empty
    - LLM output invalid

    For your current Simple Scrum Process JSON, this will generate a
    meaningful flow through the named steps instead of just Start→End.
    """
    try:
        inferred_name, inferred_edges, lane_map = _infer_edges_from_json()
        final_name = inferred_name or process_name or "process"

        # Optional LLM edges (ignored unless valid)
        parsed_edges: List[Tuple[str, str]] = []
        if isinstance(edge_list_json, str) and edge_list_json.strip():
            clean = re.sub(r'^```json\s*|```$', '', edge_list_json.strip(), flags=re.MULTILINE)
            try:
                obj = json.loads(clean)
                if isinstance(obj, list):
                    for item in obj:
                        if (
                            isinstance(item, (list, tuple))
                            and len(item) == 2
                            and str(item[0]).strip()
                            and str(item[1]).strip()
                        ):
                            parsed_edges.append((str(item[0]).strip(), str(item[1]).strip()))
            except Exception:
                logger.warning("LLM edge list invalid; ignoring")

        # Prefer inferred edges
        edges = inferred_edges or parsed_edges or [("Start", "End")]

        # Build graph
        G = nx.DiGraph()
        G.add_edges_from(edges)

        # Ensure lane_map covers all nodes
        for n in G.nodes():
            lane_map.setdefault(n, "Process")

        # Layout
        pos = _compute_positions(edges, lane_map)

        # BPMN-style coloring
        in_deg = dict(G.in_degree())
        out_deg = dict(G.out_degree())
        colors: List[str] = []
        for n in G.nodes():
            if in_deg.get(n, 0) == 0 and out_deg.get(n, 0) > 0:
                colors.append("green")   # Start-like
            elif out_deg.get(n, 0) == 0 and in_deg.get(n, 0) > 0:
                colors.append("red")     # End-like
            elif out_deg.get(n, 0) > 1:
                colors.append("orange")  # Gateway-like
            else:
                colors.append("lightblue")

        os.makedirs("output", exist_ok=True)
        filename = f"output/{final_name.lower().replace(' ', '_')}_flow.png"

        plt.figure(figsize=(14, 7))

        # Draw swimlane backgrounds
        lanes = sorted(set(lane_map.values()))
        yvals = {lane: idx for idx, lane in enumerate(lanes)}
        xmin = -0.5
        xmax = max((p[0] for p in pos.values()), default=0) + 0.5

        for lane, y in yvals.items():
            plt.axhspan(y - 0.5, y + 0.5, facecolor="#f5f5f5", alpha=0.4)
            plt.text(xmin - 0.3, y, lane, va="center", ha="right", fontsize=8, rotation=90)

        plt.xlim(xmin - 0.5, xmax + 0.5)
        plt.ylim(-0.5, len(lanes) - 0.5)

        # Draw graph
        nx.draw(
            G, pos,
            with_labels=True,
            node_color=colors,
            edge_color="gray",
            node_size=2500,
            font_size=8,
            arrows=True,
            arrowstyle="->",
            arrowsize=12,
        )

        plt.title(final_name)
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()

        return filename

    except Exception:
        logger.exception("Unexpected error while generating diagram")
        return "None"


# ============================================================
#  LLM AGENT (GENERIC, SAFE, ALWAYS VALID)
# ============================================================

edge_inference_agent = LlmAgent(
    name="Edge_Inference_Agent",
    model="gemini-2.0-flash-001",
    description="Infers flowchart edges from normalized process JSON and generates a BPMN-style swimlane diagram.",
    instruction=(
        "You are a Process Flow Inference Specialist.\n\n"
        "CONTEXT:\n"
        "- The normalized process JSON is stored in output/process_data.json.\n"
        "- It ALWAYS follows this canonical high-level schema:\n"
        "  {\n"
        "    \"process_name\": string,\n"
        "    \"version\": string,\n"
        "    \"introduction\": string,\n"
        "    \"stakeholders\": [],\n"
        "    \"process_steps\": [],\n"
        "    \"tools_summary\": {},\n"
        "    \"metrics\": [],\n"
        "    \"reporting_and_analytics\": {},\n"
        "    \"system_requirements\": [],\n"
        "    \"appendix\": {}\n"
        "  }\n"
        "- Each item in process_steps may contain fields like:\n"
        "    - step_name or name (step label)\n"
        "    - step_number, step_id, or step (ordering)\n"
        "    - dependencies (for branching)\n"
        "    - responsible_party or responsibleRole or lane (for swimlanes)\n\n"
        "YOUR TASK:\n"
        "- Conceptually infer a simple directed flow from process_steps.\n"
        "- Use step_name or name as node labels.\n"
        "- Order steps using:\n"
        "    1) step_number if present\n"
        "    2) step_id if present\n"
        "    3) step if present\n"
        "    4) list order\n"
        "- Construct a JSON array of edges:\n"
        "    [[\"A\", \"B\"], [\"B\", \"C\"]]\n"
        "- If only one step exists, use:\n"
        "    [[\"Start\", S], [S, \"End\"]]\n"
        "- If no steps exist, use:\n"
        "    [[\"Start\", \"End\"]]\n\n"
        "IMPORTANT:\n"
        "- Python will ALWAYS generate a diagram, even if your edges are empty or imperfect.\n"
        "- But you MUST still output a valid JSON array of edges to the tool.\n\n"
        "TOOL CALL CONTRACT:\n"
        "- Call generate_clean_diagram exactly once.\n"
        "- First argument: process_name.\n"
        "- Second argument: your JSON array of edges, as a string.\n"
        "- Do NOT wrap the JSON in markdown fences.\n"
        "- Do NOT output any normal text or commentary.\n"
        "- After the tool call, STOP.\n"
    ),
    tools=[generate_clean_diagram],
)
