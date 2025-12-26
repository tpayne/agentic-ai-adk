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
import sys

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
    3) step (numeric)
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

    # 3) step
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
#  LABEL ENRICHMENT
# ============================================================

def _shorten(text: str, max_len: int = 80) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _extract_step_metrics(step: dict) -> List[str]:
    """
    Extract up to 1 metric name from a step-level metrics structure.
    """
    metrics = step.get("metrics")
    if not metrics:
        return []

    names: List[str] = []
    if isinstance(metrics, dict):
        names = list(metrics.keys())
    elif isinstance(metrics, list):
        for m in metrics:
            if isinstance(m, str):
                names.append(m)
            elif isinstance(m, dict):
                n = m.get("name") or m.get("metric_name")
                if isinstance(n, str) and n.strip():
                    names.append(n.strip())

    seen = set()
    deduped = []
    for n in names:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped[:1]  # keep it tight


def _build_enriched_label(base_name: str, step: dict) -> str:
    """
    Build an enriched multi-line label, but intentionally compact:

    base_name
    Duration: <estimated_duration>
    Metric: <m1>
    """
    lines = [base_name]

    duration = step.get("estimated_duration") or step.get("duration")
    if isinstance(duration, str) and duration.strip():
        lines.append(f"Duration: {_shorten(duration, 40)}")

    metric_names = _extract_step_metrics(step)
    if metric_names:
        lines.append(f"Metric: {_shorten(metric_names[0], 40)}")

    # Leaving out success criteria here to avoid vertical sprawl.
    return "\n".join(lines)


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

        if "step_number" in s:
            val = s.get("step_number")
            index[f"step_number:{val}"] = s

        if "step_id" in s:
            val = s.get("step_id")
            index[f"step_id:{val}"] = s

        if "step" in s:
            val = s.get("step")
            index[f"step:{val}"] = s

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

def _infer_edges_from_json() -> Tuple[str | None, List[Tuple[str, str]], Dict[str, str], Dict[str, str]]:
    """
    Infer:
    - process_name
    - edges (linear + branching)
    - lane_map (base_name -> lane)
    - label_map (base_name -> enriched_label)

    ALWAYS returns at least one edge.
    """
    data = _load_process_json()
    if not data or not isinstance(data, dict):
        return "process", [("Start", "End")], {"Start": "Process", "End": "Process"}, {"Start": "Start", "End": "End"}

    process_name = data.get("process_name") or "process"

    raw_steps = data.get("process_steps") or []
    if not isinstance(raw_steps, list):
        return process_name, [("Start", "End")], {"Start": "Process", "End": "Process"}, {"Start": "Start", "End": "End"}

    valid_steps: List[dict] = []
    for s in raw_steps:
        if isinstance(s, dict):
            name = s.get("step_name") or s.get("name")
            if isinstance(name, str) and name.strip():
                valid_steps.append(s)
        elif isinstance(s, str) and s.strip():
            valid_steps.append({"name": s.strip()})

    if not valid_steps:
        return process_name, [("Start", "End")], {"Start": "Process", "End": "Process"}, {"Start": "Start", "End": "End"}

    ordered_steps = _order_steps(valid_steps)

    node_labels: List[str] = []
    lane_map: Dict[str, str] = {}
    label_map: Dict[str, str] = {}
    for s in ordered_steps:
        raw_name = s.get("step_name") or s.get("name")
        if not isinstance(raw_name, str):
            continue
        base_label = _normalize_node_label(raw_name)
        if not base_label:
            continue
        if base_label not in node_labels:
            node_labels.append(base_label)
        lane_map[base_label] = _get_lane(s)
        label_map[base_label] = _build_enriched_label(base_label, s)

    edges: List[Tuple[str, str]] = []
    if len(node_labels) == 1:
        only = node_labels[0]
        edges = [("Start", only), (only, "End")]
        lane_map["Start"] = "Process"
        lane_map["End"] = "Process"
        label_map.setdefault("Start", "Start")
        label_map.setdefault("End", "End")
    else:
        for i in range(len(node_labels) - 1):
            edges.append((node_labels[i], node_labels[i + 1]))

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

    if not edges:
        edges = [("Start", "End")]
        lane_map["Start"] = "Process"
        lane_map["End"] = "Process"
        label_map.setdefault("Start", "Start")
        label_map.setdefault("End", "End")

    return process_name, edges, lane_map, label_map


# ============================================================
#  LAYOUT (SWIMLANES + SIMPLE)
# ============================================================

def _compute_swimlane_positions(
    edges: List[Tuple[str, str]],
    lane_map: Dict[str, str],
    x_spacing: float = 3.0,
    y_spacing: float = 3.0,
) -> Dict[str, Tuple[float, float]]:
    """
    Swimlane layout:
    - y-axis = lane * y_spacing
    - x-axis = sequence index * x_spacing

    Uses tunable spacing to reduce overlap.
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
        y = lane_y[lane] * y_spacing
        for i, n in enumerate(items):
            x = i * x_spacing
            pos[n] = (x, y)

    return pos


def _compute_simple_positions(nodes: List[str]) -> Dict[str, Tuple[float, float]]:
    """
    Simple spring layout when we don't really have meaningful lanes.
    """
    G = nx.DiGraph()
    G.add_nodes_from(nodes)
    pos = nx.spring_layout(G, seed=42)
    return pos


# ============================================================
#  DIAGRAM GENERATION (ALWAYS PRODUCES SOMETHING)
# ============================================================

def generate_clean_diagram(process_name: str, edge_list_json: str) -> str:
    """
    Generates a BPMN-style diagram with auto-selected layout.

    Layout selection:
    - If multiple lanes -> vertical swimlane layout.
    - If only one lane -> simple spring layout.

    ALWAYS produces a diagram.
    """
    try:
        inferred_name, inferred_edges, lane_map, label_map = _infer_edges_from_json()
        final_name = inferred_name or process_name or "process"

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

        edges = inferred_edges or parsed_edges or [("Start", "End")]

        G = nx.DiGraph()
        G.add_edges_from(edges)

        for n in G.nodes():
            lane_map.setdefault(n, "Process")
            label_map.setdefault(n, n)

        in_deg = dict(G.in_degree())
        out_deg = dict(G.out_degree())
        nodes_in_cycles = set()
        try:
            for cycle in nx.simple_cycles(G):
                for node in cycle:
                    nodes_in_cycles.add(node)
        except Exception:
            pass

        lanes = sorted(set(lane_map.values()))
        use_swimlanes = len(lanes) > 1

        if use_swimlanes:
            max_nodes_per_lane = max(
                sum(1 for n in G.nodes() if lane_map.get(n, "Process") == lane)
                for lane in lanes
            )
            x_spacing = 3.0
            y_spacing = 3.0
            pos = _compute_swimlane_positions(edges, lane_map, x_spacing=x_spacing, y_spacing=y_spacing)

            width = max(10.0, max_nodes_per_lane * 2.5)
            height = max(6.0, len(lanes) * 1.5)
        else:
            pos = _compute_simple_positions(list(G.nodes()))
            width = 10.0
            height = 7.0

        os.makedirs("output", exist_ok=True)
        filename = f"output/{final_name.lower().replace(' ', '_')}_flow.png"

        plt.figure(figsize=(width, height))

        if use_swimlanes:
            yvals = {lane: idx for idx, lane in enumerate(lanes)}

            if pos:
                xs = [p[0] for p in pos.values()]
                min_x, max_x = min(xs), max(xs)
            else:
                min_x = max_x = 0.0

            lane_label_margin = 4.0
            xmin = min_x - 1.0
            xmax = max_x + 1.0

            for lane, row in yvals.items():
                y = row * 3.0
                plt.axhspan(y - 1.5, y + 1.5, facecolor="#f5f5f5", alpha=0.3)
                plt.text(
                    xmin - lane_label_margin,
                    y,
                    lane,
                    va="center",
                    ha="right",
                    fontsize=9,
                    bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.3"),
                )

            plt.xlim(xmin - lane_label_margin, xmax + 1.0)
            ymin = -1.5
            ymax = (len(lanes) - 1) * 3.0 + 1.5
            plt.ylim(ymin, ymax)
        else:
            if pos:
                xs = [p[0] for p in pos.values()]
                ys = [p[1] for p in pos.values()]
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
            else:
                xmin = ymin = -1.0
                xmax = ymax = 1.0
            pad = 0.5
            plt.xlim(xmin - pad, xmax + pad)
            plt.ylim(ymin - pad, ymax + pad)

        if G.nodes():
            max_label_len = max(len(label_map.get(n, str(n))) for n in G.nodes())
        else:
            max_label_len = 10

        font_size = max(6, min(10, int(180 / max_label_len)))
        node_size = max(3500, min(8000, 140 * max_label_len))

        colors: List[str] = []
        for n in G.nodes():
            if n in nodes_in_cycles:
                colors.append("purple")
            elif out_deg.get(n, 0) > 1:
                colors.append("orange")
            elif in_deg.get(n, 0) == 0 and out_deg.get(n, 0) > 0:
                colors.append("green")
            elif out_deg.get(n, 0) == 0 and in_deg.get(n, 0) > 0:
                colors.append("red")
            else:
                colors.append("lightblue")

        loop_edges = []
        normal_edges = []
        for (u, v) in G.edges():
            if u in nodes_in_cycles and v in nodes_in_cycles:
                loop_edges.append((u, v))
            else:
                normal_edges.append((u, v))

        nx.draw_networkx_edges(
            G,
            pos,
            edgelist=normal_edges,
            edge_color="gray",
            arrows=True,
            arrowstyle="->",
            arrowsize=12,
        )

        if loop_edges:
            nx.draw_networkx_edges(
                G,
                pos,
                edgelist=loop_edges,
                edge_color="gray",
                style="dashed",
                arrows=True,
                arrowstyle="->",
                arrowsize=12,
            )

        nx.draw_networkx_nodes(
            G,
            pos,
            node_color=colors,
            node_size=node_size,
        )

        nx.draw_networkx_labels(
            G,
            pos,
            labels=label_map,
            font_size=font_size,
            verticalalignment="center",
            horizontalalignment="center",
            bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.3"),
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


# ============================================================
# __main__ TEST HARNESS (DIRECT EXECUTION WITHOUT LLM)
# ============================================================
if __name__ == "__main__":

    print("\n=== Edge Inference Agent – Direct Test Harness ===")
    if len(sys.argv) < 2:
        print("Usage: python edge_inference_agent.py <path_to_json>")
        print("Example: python edge_inference_agent.py sample.json")
        sys.exit(1)

    json_path = sys.argv[1]
    if not os.path.exists(json_path):
        print(f"ERROR: File not found: {json_path}")
        sys.exit(1)

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse JSON: {e}")
        sys.exit(1)

    os.makedirs("output", exist_ok=True)
    with open("output/process_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Loaded JSON and wrote to output/process_data.json")

    process_name, edges, lane_map, label_map = _infer_edges_from_json()
    print("\nInferred process name:", process_name)
    print("Inferred edges:")
    for e in edges:
        print(" ", e)

    edges_json_str = json.dumps([[a, b] for a, b in edges])
    print("\nGenerating diagram...")
    result = generate_clean_diagram(process_name, edges_json_str)
    print("\nDiagram saved to:", result)
    print("=== Done ===\n")
