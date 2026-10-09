"""Pure matplotlib/networkx micro-BPMN subprocess diagram generator."""

import os
import logging
import textwrap
from typing import Dict, List, Optional, Tuple

import matplotlib
# Callers may invoke this from a background thread (e.g. inside
# asyncio.to_thread) -- matplotlib's default interactive GUI backend
# requires main-thread execution and warns ("Starting a Matplotlib GUI
# outside of the main thread will likely fail.") the moment pyplot is used
# from anywhere else -- confirmed directly. This module never calls
# plt.show(), only fig.savefig(), so the non-interactive "Agg" backend is
# strictly correct here, not a workaround. Must be set before pyplot is
# ever imported (its backend is selected at import time).
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402

from process_toolkit.filenames import safe_filename_component
from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.StepDiagram")


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

def generate_step_diagram_for_step(
    step_name: str, subprocess_json: dict, output_dir: Optional[str] = None,
) -> str:
    """
    Robust subprocess diagram generator.
    - No label clipping
    - Labels drawn OUTSIDE nodes
    - Auto-wrap long labels
    - Larger canvas

    `output_dir` defaults to the relative path "output/step_diagrams" if
    not given; pass an absolute path to control exactly where images are
    written (e.g. a caller-resolved, possibly test-isolated output root).
    """
    try:
        substeps = _extract_substeps(subprocess_json)
        if not substeps:
            logger.debug(f"No substeps for '{step_name}', skipping diagram.")
            return ""

        output_dir = output_dir or paths.output_dir("step_diagrams")

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

        # Output path. step_name is caller-supplied (LLM-generated process
        # step content, not a trusted filename) -- safe_filename_component
        # collapses it to a single safe path component instead of a bare
        # space/slash replacement, which would leave "../" sequences and
        # other reserved characters untouched. The resolved path is then
        # double-checked to still be inside output_dir before writing.
        safe_name = safe_filename_component(step_name)
        out_path = os.path.join(output_dir, f"{safe_name}.png")

        resolved_dir = os.path.realpath(output_dir)
        resolved_path = os.path.realpath(out_path)
        if os.path.commonpath([resolved_dir, resolved_path]) != resolved_dir:
            logger.error(
                f"Refusing to write outside {output_dir}: "
                f"step_name={step_name!r} resolved to {resolved_path!r}"
            )
            return ""
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
        # Swimlane labels are drawn via ax.text(xmin - 5.0, ...), which can
        # sit arbitrarily far left of the Axes' own data range for a long
        # responsible_party name -- fig.tight_layout()'s subplot-margin
        # heuristic can't reconcile that with fig.suptitle()'s own padding,
        # and warns ("Tight layout not applied") on every real multi-lane
        # diagram with long-enough lane names, confirmed directly. Dropping
        # it in favor of bbox_inches="tight" at save time (matching
        # edge_inference.py's own diagram save) crops to the actual
        # rendered content -- including the out-of-axes lane labels --
        # instead of trying to pre-compute subplot margins for it.
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.debug(f"Step diagram generated at {out_path}")
        return out_path

    except Exception:
        logger.exception(f"Failed to generate step diagram for '{step_name}'")
        return ""
