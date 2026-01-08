# process_agents/edge_inference_agent.py

from google.adk.agents import LlmAgent
from google.genai import types
import os
import json
import traceback
import networkx as nx
import matplotlib.pyplot as plt
import logging
from typing import List, Tuple, Any, Dict
import sys

from .utils import load_instruction

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
      "industry_sector": string,
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
    Build a multi-line label with full text, no truncation.
    """
    lines = [base_name]

    duration = step.get("estimated_duration") or step.get("duration")
    if isinstance(duration, str) and duration.strip():
        lines.append(f"Duration: {duration.strip()}")

    metric_names = _extract_step_metrics(step)
    if metric_names:
        lines.append(f"Metric: {metric_names[0]}")

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
        logger.warning("No valid process JSON; using fallback Start→End")
        return "process", [("Start", "End")], {"Start": "Process", "End": "Process"}, {"Start": "Start", "End": "End"}

    process_name = data.get("process_name") or "process"

    raw_steps = data.get("process_steps") or []
    if not isinstance(raw_steps, list):
        logger.warning("process_steps is not a list; using fallback Start→End")
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
        logger.warning("No valid steps inferred; using fallback Start→End")
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
        logger.warning("No edges inferred; using fallback Start→End")
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
    x_spacing: float = 4.5,
    y_spacing: float = 4.0,
) -> Dict[str, Tuple[float, float]]:
    """
    Swimlane layout:
    - y-axis = lane * y_spacing
    - x-axis = sequence index * x_spacing

    Spacing is intentionally generous to reduce overlap and clipping.
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

def generate_clean_diagram() -> str:
    """
    Generates a refined process architecture diagram as a PNG image.
    This function restores circular node styles and the original color schema, 
    retains swimlane backgrounds for organizational clarity, and implements 
    text wrapping for node labels to prevent clipping. The diagram is laid out 
    with nodes grouped by swimlanes, edges drawn with arrows, and nodes styled 
    for readability. The output image is saved to 'output/process_flow.png'.
    Returns:
        str: A message indicating the success or failure of the diagram generation.
    """
    import textwrap
    logger.info("Generating final diagram: Tidied Bisected Circle with visible Arrowheads...")
    
    try:
        # LOAD DATA
        inferred_name, inferred_edges, lane_map, label_map = _infer_edges_from_json()
        final_name = (inferred_name or "Process Architecture").strip()
        edges = inferred_edges or []
        
        G = nx.DiGraph()
        G.add_edges_from(edges)
        
        for n in G.nodes():
            lane_map.setdefault(n, "Process")
            label_map.setdefault(n, n)

        # IDENTIFY START AND END (Logic-based)
        # Start = No incoming edges; End = No outgoing edges
        start_nodes = [n for n, d in G.in_degree() if d == 0]
        end_nodes = [n for n, d in G.out_degree() if d == 0]

        # 1. POSITIONING
        x_spacing, y_spacing = 5.0, -4.0 
        nodes = list(G.nodes())
        lanes = sorted(list(set(lane_map.get(n, "Process") for n in nodes)))
        lane_y_indices = {lane: idx for idx, lane in enumerate(lanes)}
        
        lane_positions = {lane: [] for lane in lanes}
        for n in nodes:
            lane = lane_map.get(n, "Process")
            lane_positions[lane].append(n)
        
        pos = {}
        for lane, items in lane_positions.items():
            y = lane_y_indices[lane] * y_spacing
            for i, n in enumerate(items):
                x = i * x_spacing
                pos[n] = (x, y)

        # 2. SETUP CANVAS
        fig, ax = plt.subplots(figsize=(18, 10))

        # 3. DRAW SWIMLANES
        lane_colors = plt.cm.get_cmap("Pastel1", len(lanes))
        for i, lane in enumerate(lanes):
            y_coord = lane_y_indices[lane] * y_spacing
            ax.axhspan(y_coord - 1.8, y_coord + 1.8, color=lane_colors(i), alpha=0.10)
            ax.text(-3.0, y_coord, lane.upper(), va='center', ha='right', 
                    fontsize=11, fontweight='bold', color="#555555")

        # 4. DRAW EDGES
        nx.draw_networkx_edges(
            G, pos, ax=ax, edge_color="#7f8c8d", arrows=True, 
            arrowstyle='-|>', arrowsize=20, width=1.5, 
            connectionstyle="arc3,rad=0.1", min_source_margin=30, min_target_margin=30 
        )

        # 5. DRAW BISECTED NODES
        for node in nodes:
            x, y = pos[node]
            label = label_map.get(node, node)
            wrapped_text = "\n".join(textwrap.wrap(label, width=28))

            # BOLD PURE COLOR LOGIC
            if node in start_nodes:
                fill_color = "#15B615" # Pure Green
                line_color = "#006400" # Deep Green Border
                text_weight = "bold"
            elif node in end_nodes:
                fill_color = "#FF0000" # Pure Red
                line_color = "#8B0000" # Deep Red Border
                text_weight = "bold"
            else:
                fill_color = "#D5E8F7" # Standard Blue
                line_color = "#2980B9" # Standard Steel Blue
                text_weight = "medium"

            # A. Background Circle
            ax.plot(x, y, marker='o', markersize=62, 
                    markeredgecolor=line_color, markerfacecolor=fill_color, 
                    linestyle='None')

            # B. Bisecting Text Box
            ax.text(
                x, y, wrapped_text,
                ha="center", va="center",
                fontsize=9, fontweight=text_weight,
                bbox=dict(
                    facecolor="white", 
                    edgecolor=line_color, 
                    boxstyle="round,pad=0.5", 
                    linewidth=1.5
                )
            )

        # 6. VIEWPORT
        if pos:
            x_vals, y_vals = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
            ax.set_xlim(min(x_vals) - 5.5, max(x_vals) + 5.5)
            ax.set_ylim(min(y_vals) - 3.5, max(y_vals) + 3.5)
        
        plt.title(f"Process Architecture: {final_name}", fontsize=15, pad=30, fontweight='bold')
        plt.axis("off")

        # 7. SAVE
        out_path = "output/process_flow.png"
        if process_name:
            out_path = f"output/{process_name.lower().replace(' ', '_')}_flow.png"
        else:
            out_path = "output/process_flow.png"

        fig.tight_layout()
        plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        return f"Diagram successfully generated at {out_path}"

    except Exception as e:
        logger.error(f"Failed to generate diagram: {e}")
        return f"Diagram generation failed: {str(e)}"
        
# ============================================================
#  LLM AGENT (NO LARGE ARGS, TOOL CALL BY NAME ONLY)
# ============================================================
edge_inference_agent = LlmAgent(
    name="Edge_Inference_Agent",
    model="gemini-2.0-flash-001",
    description="Triggers BPMN-style swimlane diagram generation based only on process_name.",
    instruction=load_instruction("edge_inference_agent.txt"),
    include_contents="none",
    tools=[generate_clean_diagram],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
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

    print("\nGenerating diagram...")
    result = generate_clean_diagram()
    print("\nDiagram saved to:", result)
    print("=== Done ===\n")
