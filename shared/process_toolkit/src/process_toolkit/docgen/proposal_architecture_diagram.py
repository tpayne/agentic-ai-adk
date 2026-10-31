"""Renders a simple, deterministic solution-architecture diagram from
proposal_response.json's own "architecture_components" field (list of
{"name", "description", "connects_to": [...]}) -- one labeled node per
component, one directed edge per "connects_to" entry.

Mirrors edge_inference.py's generate_clean_diagram's own node-circle +
wrapped-text-label + arrow drawing style for visual consistency with the
rest of this project's generated diagrams, but with a much simpler
layout: architecture components have no "lane" concept the way process
steps/design components do, so nodes are positioned purely by BFS depth
from root nodes (in_degree() == 0) -- depth drives the X axis, index-
within-depth-level drives the Y axis, centered. No swimlane engine, no
topological-sort-for-X-position complexity.

Self-contained and called directly by generation.py's own document-build
step (_add_solution_architecture_section), NOT wired through
Proposal_Response_Pipeline's edge_inference stage -- that stage's own
no-op guard for schema_type == "proposal_response" stays untouched. Same
reasoning _add_flowchart_section(..., generate_diagram=True) already
uses for process/design: a diagram generated at document-build time
doesn't need a separate prior agent tool call.
"""

import logging
import textwrap
from typing import Any, Dict, List, Tuple

import matplotlib as mpl
# Must be set before pyplot is imported -- same reasoning as
# edge_inference.py's own identical line (this module only ever calls
# plt.savefig(), never plt.show(), and may run inside a background
# thread).
mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402

from process_toolkit import paths
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

    x_spacing, y_spacing = 5.0, -3.5
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

    fig, ax = plt.subplots(figsize=(14, 8))

    nx.draw_networkx_edges(
        G, pos, ax=ax, edge_color="#7f8c8d", arrows=True,
        arrowstyle='-|>', arrowsize=20, width=1.5,
        connectionstyle="arc3,rad=0.1", min_source_margin=30, min_target_margin=30,
    )

    for name in G.nodes():
        x, y = pos.get(name, (0.0, 0.0))
        wrapped_text = "\n".join(textwrap.wrap(name, width=24))
        ax.plot(
            x, y, marker='o', markersize=62,
            markeredgecolor="#2980B9", markerfacecolor="#D5E8F7", linestyle='None',
        )
        ax.text(
            x, y, wrapped_text, ha="center", va="center",
            fontsize=9, fontweight="normal",
            bbox=dict(facecolor="white", edgecolor="#2980B9", boxstyle="round,pad=0.5", linewidth=1.5),
        )

    if pos:
        x_vals = [p[0] for p in pos.values()]
        y_vals = [p[1] for p in pos.values()]
        ax.set_xlim(min(x_vals) - 4.0, max(x_vals) + 4.0)
        ax.set_ylim(min(y_vals) - 3.0, max(y_vals) + 3.0)

    plt.title(f"Solution Architecture: {process_name}", fontsize=15, pad=30, fontweight='bold')
    plt.axis("off")

    out_path = paths.output_path(f"{safe_filename_component(process_name.lower())}_architecture.png")

    fig.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    return out_path
