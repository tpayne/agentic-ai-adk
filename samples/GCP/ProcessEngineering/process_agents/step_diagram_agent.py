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
    Robust subprocess diagram generator.
    - No label clipping
    - Labels drawn OUTSIDE nodes
    - Auto-wrap long labels
    - Larger canvas
    """
    try:
        substeps = _extract_substeps(subprocess_json)
        if not substeps:
            logger.debug(f"No substeps for '{step_name}', skipping diagram.")
            return ""

        # Build nodes + edges
        nodes: List[str] = []
        edges: List[Tuple[str, str]] = []
        lane_map: Dict[str, str] = {}
        label_map: Dict[str, str] = {}

        root = step_name
        nodes.append(root)
        lane_map[root] = "Process"
        label_map[root] = root

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

        for i in range(len(substeps)):
            if i == 0:
                edges.append((root, nodes[i + 1]))
            else:
                edges.append((nodes[i], nodes[i + 1]))

        G = nx.DiGraph()
        G.add_edges_from(edges)

        lanes = sorted(set(lane_map.values()))
        use_swimlanes = len(lanes) > 1

        # Layout
        if use_swimlanes:
            lane_y = {lane: idx for idx, lane in enumerate(lanes)}
            pos = {}
            lane_positions = {lane: [] for lane in lanes}
            for n in nodes:
                lane_positions[lane_map[n]].append(n)
            for lane, items in lane_positions.items():
                for i, n in enumerate(items):
                    pos[n] = (i * 4.0, lane_y[lane] * 4.0)
        else:
            pos = nx.spring_layout(G, seed=42)

        # Output path
        safe_name = step_name.replace(" ", "_").replace("/", "_")
        out_path = os.path.join(OUTPUT_DIR, f"{safe_name}.png")
        # Large canvas
        fig, ax = plt.subplots(figsize=(18, 10))
        ax.axis("off")

        # Swimlane shading
        if use_swimlanes:
            yvals = {lane: idx for idx, lane in enumerate(lanes)}
            xs = [p[0] for p in pos.values()]
            xmin, xmax = min(xs), max(xs)
            for lane, row in yvals.items():
                y = row * 4.0
                ax.axhspan(y - 2.0, y + 2.0, facecolor="#f5f5f5", alpha=0.3)
                ax.text(
                    xmin - 5.0,
                    y,
                    lane,
                    va="center",
                    ha="right",
                    fontsize=10,
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
            ax=ax,
        )

        # Draw nodes (NO LABELS)
        node_colors = ["lightgray" if n == root else "lightblue" for n in nodes]
        nx.draw_networkx_nodes(
            G,
            pos,
            node_color=node_colors,
            node_size=5000,
            ax=ax,
        )

        # Draw labels OUTSIDE nodes
        for n, (x, y) in pos.items():
            label = label_map[n]

            # Wrap long labels
            import textwrap
            wrapped = "\n".join(textwrap.wrap(label, width=28))

            ax.text(
                x,
                y,
                wrapped,
                ha="center",
                va="center",
                fontsize=10,
                bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.3"),
            )

        fig.suptitle(step_name, fontsize=14)
        fig.tight_layout()
        fig.savefig(out_path, dpi=150)
        plt.close(fig)

        logger.debug(f"Step diagram generated at {out_path}")
        return out_path

    except Exception:
        logger.exception(f"Failed to generate step diagram for '{step_name}'")
        return ""
