# process_agents/step_diagram_agent.py

import os
import logging
import matplotlib.pyplot as plt
import networkx as nx
from typing import Dict, List, Tuple, Any

logger = logging.getLogger("ProcessArchitect.StepDiagram")

OUTPUT_DIR = "output/step_diagrams"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ------------------------------------------------------------
#  SCHEMA-AGNOSTIC SUBSTEP EXTRACTION
# ------------------------------------------------------------

def _extract_substeps(subprocess_json: dict) -> list:
    if not isinstance(subprocess_json, dict):
        return []

    candidate_keys = [
        "subprocess_steps",
        "subprocess_flow",
        "steps",
        "flow",
        "phases",
        "substeps",
        "activities",
    ]

    for key in candidate_keys:
        if key in subprocess_json and isinstance(subprocess_json[key], list):
            return subprocess_json[key]

    # fallback: any list of dicts
    for _, v in subprocess_json.items():
        if isinstance(v, list) and all(isinstance(x, dict) for x in v):
            return v

    return []


# ------------------------------------------------------------
#  SWIMLANE + LABEL HELPERS (MATCH EDGE AGENT)
# ------------------------------------------------------------

def _get_lane(sub: dict) -> str:
    lane = (
        sub.get("lane")
        or sub.get("responsible_party")
        or sub.get("responsibleRole")
        or "Process"
    )
    if isinstance(lane, list) and lane:
        return str(lane[0])
    if isinstance(lane, str):
        return lane.strip()
    return "Process"


def _normalize_label(name: str) -> str:
    return name.strip()


def _is_gateway(sub: dict) -> bool:
    if not isinstance(sub, dict):
        return False
    if sub.get("type", "").lower() in {"gateway", "decision"}:
        return True
    if "condition" in sub or "branch_condition" in sub:
        return True
    return False


# ------------------------------------------------------------
#  PURE PYTHON MICRO-BPMN DIAGRAM GENERATION
# ------------------------------------------------------------

def generate_step_diagram_for_step(step_name: str, subprocess_json: dict) -> str:
    """
    Pure Python diagram generator for subprocess flows.
    Uses the SAME rendering engine as edge_inference_agent:
    - matplotlib
    - networkx
    - swimlane layout
    - PNG output
    """
    try:
        substeps = _extract_substeps(subprocess_json)
        if not substeps:
            logger.info(f"No substeps for '{step_name}', skipping diagram.")
            return ""

        # Build nodes + edges
        nodes: List[str] = []
        edges: List[Tuple[str, str]] = []
        lane_map: Dict[str, str] = {}
        label_map: Dict[str, str] = {}

        # Root node
        root = f"{step_name}"
        nodes.append(root)
        lane_map[root] = "Process"
        label_map[root] = root

        # Substep nodes
        for idx, sub in enumerate(substeps, start=1):
            name = (
                sub.get("substep_name")
                or sub.get("step_name")
                or sub.get("name")
                or f"Sub-step {idx}"
            )
            name = _normalize_label(name)
            nodes.append(name)
            lane_map[name] = _get_lane(sub)
            label_map[name] = name

        # Default linear flow
        for i in range(len(substeps)):
            if i == 0:
                edges.append((root, nodes[i + 1]))
            else:
                edges.append((nodes[i], nodes[i + 1]))

        # Build graph
        G = nx.DiGraph()
        G.add_edges_from(edges)

        # Compute swimlane layout (same logic as edge agent)
        lanes = sorted(set(lane_map.values()))
        use_swimlanes = len(lanes) > 1

        if use_swimlanes:
            lane_y = {lane: idx for idx, lane in enumerate(lanes)}
            pos: Dict[str, Tuple[float, float]] = {}
            lane_positions: Dict[str, List[str]] = {lane: [] for lane in lanes}

            for n in nodes:
                lane_positions[lane_map[n]].append(n)

            for lane, items in lane_positions.items():
                for i, n in enumerate(items):
                    pos[n] = (i * 3.0, lane_y[lane] * 3.0)
        else:
            pos = nx.spring_layout(G, seed=42)

        # Render
        safe_name = step_name.replace(" ", "_").replace("/", "_")
        out_path = os.path.join(OUTPUT_DIR, f"{safe_name}.png")

        plt.figure(figsize=(10, 6))

        # Draw swimlane backgrounds
        if use_swimlanes:
            yvals = {lane: idx for idx, lane in enumerate(lanes)}
            xs = [p[0] for p in pos.values()]
            min_x, max_x = min(xs), max(xs)
            for lane, row in yvals.items():
                y = row * 3.0
                plt.axhspan(y - 1.5, y + 1.5, facecolor="#f5f5f5", alpha=0.3)
                plt.text(
                    min_x - 2.0,
                    y,
                    lane,
                    va="center",
                    ha="right",
                    fontsize=9,
                    bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.3"),
                )

        # Draw edges
        nx.draw_networkx_edges(
            G,
            pos,
            edge_color="gray",
            arrows=True,
            arrowstyle="->",
            arrowsize=12,
        )

        # Draw nodes
        node_colors = []
        for n in nodes:
            if n == root:
                node_colors.append("lightgray")
            else:
                node_colors.append("lightblue")

        nx.draw_networkx_nodes(
            G,
            pos,
            node_color=node_colors,
            node_size=4000,
        )

        # Draw labels
        nx.draw_networkx_labels(
            G,
            pos,
            labels=label_map,
            font_size=9,
            bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.3"),
        )

        plt.title(step_name)
        plt.subplots_adjust(left=0.15, right=0.95, top=0.90, bottom=0.10)
        plt.savefig(out_path)
        plt.close()

        logger.info(f"Step diagram generated at {out_path}")
        return out_path

    except Exception:
        logger.exception(f"Failed to generate step diagram for '{step_name}'")
        return ""
