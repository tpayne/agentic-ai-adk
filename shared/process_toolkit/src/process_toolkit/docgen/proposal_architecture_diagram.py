"""Renders a polished, deterministic solution-architecture diagram from
proposal_response.json's own "architecture_components" field (list of
{"name", "description", "connects_to": [...]}) -- one capability card
per component, one directed edge per "connects_to" entry.

Components are arranged into left-to-right layers by BFS depth from root
nodes (in_degree() == 0), with siblings centered vertically. The diagram
uses a restrained enterprise palette, readable capability cards, and
directional connectors to create a client-facing system-context visual.

Self-contained and called directly by generation.py's own document-build
step (_add_solution_architecture_section), NOT wired through
Proposal_Response_Pipeline's edge_inference stage -- that stage's own
no-op guard for schema_type == "proposal_response" stays untouched. Same
reasoning _add_flowchart_section(..., generate_diagram=True) already
uses for process/design: a diagram generated at document-build time
doesn't need a separate prior agent tool call.
"""

import logging
from typing import Any, Dict, List, Tuple

import matplotlib as mpl
# Must be set before pyplot is imported -- same reasoning as
# edge_inference.py's own identical line (this module only ever calls
# plt.savefig(), never plt.show(), and may run inside a background
# thread).
mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle

from process_toolkit import paths
from process_toolkit.docgen.diagram_style import add_fitted_text, fit_title
from process_toolkit.filenames import safe_filename_component

logger = logging.getLogger("ProcessArchitect.ProposalArchitectureDiagram")


def _layered_component_positions(components: List[Dict[str, Any]]) -> Tuple[nx.DiGraph, Dict[str, Tuple[float, float]]]:
    """Builds the component graph and a deterministic left-to-right
    layered layout: BFS depth from root nodes (in_degree() == 0) drives
    X, index within each depth level (centered) drives Y. A component
    disconnected from every root (shouldn't normally happen for a real
    architecture) still renders, at depth 0."""
    names = [c["name"] for c in components]
    G = nx.DiGraph()
    G.add_nodes_from(names)
    for c in components:
        for target in c.get("connects_to") or []:
            if target in names and target != c["name"]:
                G.add_edge(c["name"], target)

    roots = [n for n in G.nodes() if G.in_degree(n) == 0] or names[:1]

    depth: Dict[str, int] = {r: 0 for r in roots}
    frontier = list(roots)
    while frontier:
        next_frontier = []
        for n in frontier:
            for succ in G.successors(n):
                if succ not in depth:
                    depth[succ] = depth[n] + 1
                    next_frontier.append(succ)
        frontier = next_frontier
    for n in names:
        depth.setdefault(n, 0)

    by_depth: Dict[int, List[str]] = {}
    for n in names:
        by_depth.setdefault(depth[n], []).append(n)

    x_spacing, y_spacing = 3.4, -2.8
    pos: Dict[str, Tuple[float, float]] = {}
    for d, nodes_at_depth in by_depth.items():
        count = len(nodes_at_depth)
        for i, n in enumerate(nodes_at_depth):
            y = (i - (count - 1) / 2.0) * y_spacing
            pos[n] = (d * x_spacing, y)

    return G, pos


def generate_proposal_architecture_diagram(components: List[Dict[str, Any]], process_name: str) -> str:
    """Renders the diagram and saves it to
    output/<process_name>_architecture.png. Returns the saved path.

    Raises ValueError if `components` has no usable (named) entries --
    the caller's own responsibility to skip calling this at all when
    "architecture_components" is empty, same no-fabrication convention
    every other section renderer in this project follows."""
    valid = [c for c in (components or []) if isinstance(c, dict) and c.get("name")]
    if not valid:
        raise ValueError("No usable architecture_components entries to render.")

    G, pos = _layered_component_positions(valid)

    card_width, card_height = 2.55, 2.4
    x_vals = [p[0] for p in pos.values()]
    y_vals = [p[1] for p in pos.values()]
    x_min, x_max = min(x_vals), max(x_vals)
    y_min, y_max = min(y_vals), max(y_vals)
    left, right = x_min - 1.45, x_max + 1.45
    if right - left < 8.5:
        extra_padding = (8.5 - (right - left)) / 2
        left -= extra_padding
        right += extra_padding
    bottom, top = y_min - 1.55, y_max + 2.65
    plot_width, plot_height = right - left, top - bottom

    # Keep text legible when the document inserts the image at page width;
    # grow the canvas only as needed for unusually large graphs.
    fig_width = min(12.0, max(8.5, plot_width * 0.72))
    fig_height = fig_width * plot_height / plot_width
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor="#F4F7FB")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.set_facecolor("#F4F7FB")
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_aspect("equal", adjustable="box")

    # Header block
    ax.add_patch(FancyBboxPatch(
        (left, top - 1.25), plot_width, 1.25,
        boxstyle="round,pad=0.02,rounding_size=0.16",
        facecolor="#14243A", edgecolor="none", zorder=1,
    ))
    ax.text(
        left + 0.35, top - 0.47, "SYSTEM ARCHITECTURE",
        color="#77D6C1", fontsize=9, fontweight="bold", va="center",
        ha="left", zorder=2,
    )
    title = str(process_name)
    fit_title(
        ax, title, left + 0.35, top - 0.91, plot_width - 4.5,
        color="white", fontweight="bold", ha="left", zorder=2,
    )
    ax.text(
        right - 0.3, top - 0.72, f"{len(G.nodes):02d} ARCHITECTURE COMPONENTS",
        color="#D3DFEC", fontsize=8, fontweight="bold", va="center",
        ha="right", zorder=2,
    )

    layers: Dict[float, List[str]] = {}
    for name, (x, _) in pos.items():
        layers.setdefault(x, []).append(name)
    for layer_number, (x, names_at_layer) in enumerate(sorted(layers.items()), start=1):
        ax.add_patch(FancyBboxPatch(
            (x - 1.52, bottom + 0.18), 3.04, plot_height - 1.65,
            boxstyle="round,pad=0.02,rounding_size=0.12",
            facecolor="#E9EFF7" if layer_number % 2 else "#EEF3F8",
            edgecolor="#DCE5EF", linewidth=0.8, zorder=0,
        ))
        add_fitted_text(
            ax, f"LAYER {layer_number:02d}  |  {len(names_at_layer)}",
            x - 1.3, top - 1.58, 2.6, 0.28,
            fontsize=7, min_fontsize=5.5, color="#64758A",
            fontweight="bold", ha="center", zorder=2,
        )

    node_boxes = {}
    for name in G.nodes:
        x, y = pos[name]
        box = FancyBboxPatch(
            (x - card_width / 2, y - card_height / 2),
            card_width, card_height,
            boxstyle="round,pad=0.04,rounding_size=0.13",
            facecolor="white", edgecolor="#D8E1EC", linewidth=1.0,
            zorder=3,
        )
        ax.add_patch(box)
        node_boxes[name] = box

    node_order = {name: index for index, name in enumerate(G.nodes)}
    for source, target in G.edges:
        source_pos, target_pos = pos[source], pos[target]
        curve = 0.12 if node_order[source] <= node_order[target] else -0.12
        edge = FancyArrowPatch(
            source_pos, target_pos,
            patchA=node_boxes[source], patchB=node_boxes[target],
            arrowstyle="-|>", mutation_scale=13,
            connectionstyle=f"arc3,rad={curve}",
            color="#7C91AA", linewidth=1.55, alpha=0.9,
            shrinkA=4, shrinkB=4, zorder=2,
        )
        ax.add_patch(edge)

    palette = ["#2878B8", "#7258B5", "#178C83", "#D08034"]
    for index, name in enumerate(G.nodes, start=1):
        x, y = pos[name]
        color = palette[(index - 1) % len(palette)]
        ax.add_patch(Circle(
            (x - card_width / 2 + 0.24, y + 0.42), 0.14,
            facecolor=color, edgecolor="none", zorder=4,
        ))
        ax.text(
            x - card_width / 2 + 0.24, y + 0.42, f"{index:02d}",
            color="white", fontsize=6.5, fontweight="bold",
            ha="center", va="center", zorder=5,
        )
        add_fitted_text(
            ax, name, x - card_width / 2 + 0.48, y + 0.42,
            card_width - 0.68, 0.58, fontsize=9.5, min_fontsize=6.5,
            color="#1C2D43", fontweight="bold", ha="left", zorder=5,
        )
        description = next(
            (str(component.get("description", "")).strip()
             for component in valid if component["name"] == name),
            "",
        )
        if description:
            add_fitted_text(
                ax, description, x - card_width / 2 + 0.22, y - 0.17,
                    card_width - 0.44, 0.85, fontsize=7.1, min_fontsize=5.2,
                color="#64758A", ha="left", va="top", linespacing=1.15, zorder=5,
            )
        ax.add_patch(FancyBboxPatch(
            (x - card_width / 2 + 0.22, y - card_height / 2 + 0.06),
            0.38, 0.045,
            boxstyle="round,pad=0.01,rounding_size=0.02",
            facecolor=color, edgecolor="none", zorder=5,
        ))

    ax.axis("off")

    out_path = paths.output_path(f"{safe_filename_component(process_name.lower())}_architecture.png")

    plt.savefig(out_path, dpi=220, facecolor="#F4F7FB")
    plt.close(fig)

    return out_path
