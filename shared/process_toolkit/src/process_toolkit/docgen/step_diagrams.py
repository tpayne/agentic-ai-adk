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
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

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

        lanes = list(dict.fromkeys(lane_map.values()))
        lane_y = {lane: idx for idx, lane in enumerate(lanes)}
        pos = {
            n: (idx * 4.3, lane_y[lane_map[n]] * -3.2)
            for idx, n in enumerate(nodes)
        }

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
        card_width, card_height = 3.45, 1.65
        x_values = [point[0] for point in pos.values()]
        y_values = [point[1] for point in pos.values()]
        left, right = min(x_values) - 7.0, max(x_values) + 3.0
        bottom, top = min(y_values) - 2.5, max(y_values) + 3.0
        plot_width, plot_height = right - left, top - bottom
        fig_width = min(13.0, max(9.0, plot_width * 0.66))
        fig_height = fig_width * plot_height / plot_width
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor="#F4F7FB")
        ax.set_facecolor("#F4F7FB")

        ax.add_patch(FancyBboxPatch(
            (left, top - 1.55), plot_width, 1.55,
            boxstyle="round,pad=0.02,rounding_size=0.18",
            facecolor="#14243A", edgecolor="none", zorder=1,
        ))
        ax.text(
            left + 0.45, top - 0.55, "SUBPROCESS FLOW",
            color="#77D6C1", fontsize=9, fontweight="bold",
            va="center", ha="left", zorder=2,
        )
        ax.text(
            left + 0.45, top - 1.08, textwrap.shorten(step_name, 58, placeholder="..."),
            color="white", fontsize=17, fontweight="bold",
            va="center", ha="left", zorder=2,
        )
        ax.text(
            right - 0.35, top - 0.82, f"{len(nodes):02d} PROCESS STEPS",
            color="#D3DFEC", fontsize=8, fontweight="bold",
            va="center", ha="right", zorder=2,
        )

        lane_colors = ["#E9EFF7", "#EEF3F8"]
        for index, lane in enumerate(lanes):
            y_coord = lane_y[lane] * -3.2
            ax.axhspan(
                y_coord - 1.85, y_coord + 1.85,
                color=lane_colors[index % len(lane_colors)], zorder=0,
            )
            ax.text(
                left + 0.25, y_coord, textwrap.shorten(lane.upper(), 26, placeholder="..."),
                va="center", ha="left", fontsize=8, fontweight="bold",
                color="#64758A", zorder=1,
            )

        node_cards = {}
        for n in nodes:
            x, y = pos[n]
            card = FancyBboxPatch(
                (x - card_width / 2, y - card_height / 2),
                card_width, card_height,
                boxstyle="round,pad=0.04,rounding_size=0.14",
                facecolor="white", edgecolor="#D8E1EC", linewidth=1.0, zorder=3,
            )
            ax.add_patch(card)
            node_cards[n] = card

        for source, target in G.edges:
            ax.add_patch(FancyArrowPatch(
                pos[source], pos[target],
                patchA=node_cards[source], patchB=node_cards[target],
                arrowstyle="-|>", mutation_scale=14,
                connectionstyle="arc3,rad=0.08",
                color="#7C91AA", linewidth=1.6, zorder=2,
                shrinkA=4, shrinkB=4,
            ))

        end_nodes = {node for node, degree in G.out_degree() if degree == 0}
        substep_by_name = {
            sub.get("substep_name") or sub.get("step_name") or sub.get("name") or f"Sub-step {index}": sub
            for index, sub in enumerate(substeps, start=1)
        }
        for index, n in enumerate(nodes, start=1):
            x, y = pos[n]
            color = "#178C83" if n == root else "#D08034" if n in end_nodes else "#2878B8"
            substep = substep_by_name.get(n, {})
            is_decision = _is_gateway(substep)
            label = label_map[n]
            ax.add_patch(Circle(
                (x - card_width / 2 + 0.3, y + 0.43), 0.16,
                facecolor="#D08034" if is_decision else color,
                edgecolor="none", zorder=4,
            ))
            ax.text(
                x - card_width / 2 + 0.3, y + 0.43, f"{index:02d}",
                color="white", fontsize=6.5, fontweight="bold",
                ha="center", va="center", zorder=5,
            )
            ax.text(
                x - card_width / 2 + 0.58, y + 0.43,
                "\n".join(textwrap.wrap(label, width=20, break_long_words=False)[:2]),
                color="#1C2D43", fontsize=9.5, fontweight="bold",
                ha="left", va="center", zorder=5,
            )
            if is_decision:
                ax.text(
                    x - card_width / 2 + 0.28, y - 0.2,
                    textwrap.shorten(str(substep.get("condition") or substep.get("branch_condition") or "Decision"), 42, placeholder="..."),
                    color="#D08034", fontsize=7, fontweight="bold",
                    ha="left", va="top", zorder=5,
                )
            ax.add_patch(FancyBboxPatch(
                (x - card_width / 2 + 0.28, y - card_height / 2 + 0.12),
                0.42, 0.05, boxstyle="round,pad=0.01,rounding_size=0.02",
                facecolor="#D08034" if is_decision else color,
                edgecolor="none", zorder=5,
            ))

        ax.set_xlim(left, right)
        ax.set_ylim(bottom, top)
        ax.set_aspect("equal", adjustable="box")
        ax.axis("off")
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        fig.savefig(out_path, dpi=220, facecolor="#F4F7FB")
        plt.close(fig)

        logger.debug(f"Step diagram generated at {out_path}")
        return out_path

    except Exception:
        logger.exception(f"Failed to generate step diagram for '{step_name}'")
        return ""
