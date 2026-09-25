# process_agents/edge_inference_agent.py

from google.genai import types
import os
import json
import traceback
import networkx as nx
import matplotlib as mpl
import matplotlib.pyplot as plt
import logging
from typing import List, Tuple, Any, Dict
import sys

from .utils import _detect_schema_type_from_disk, safe_filename_component

logger = logging.getLogger("ProcessArchitect.EdgeInference")


def _get_lane_colormap(n: int):
    """
    Returns an n-level discrete colormap ("Pastel1"), across old and new
    matplotlib versions. matplotlib.pyplot.cm.get_cmap(name, lut) was
    deprecated in 3.7 and removed entirely in 3.9+ -- calling it there
    raises AttributeError, which was silently swallowed by generate_clean_
    diagram's try/except and surfaced only as "Diagram generation failed:
    module 'matplotlib.cm' has no attribute 'get_cmap'", so no PNG was
    ever produced. matplotlib.colormaps[name].resampled(n) is the
    replacement API (available since 3.5), tried first; the old
    plt.cm.get_cmap call remains as a fallback for any environment still
    on an older matplotlib where colormaps/resampled aren't available.
    """
    n = max(int(n), 1)
    try:
        return mpl.colormaps["Pastel1"].resampled(n)
    except Exception:
        return plt.cm.get_cmap("Pastel1", n)


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


def _load_design_json(path: str = "output/design_data.json") -> dict | None:
    """
    Load the normalized architectural design document JSON from disk.

    Relevant high-level schema (design_document_schema.json):

    {
      "document_metadata": {"title": string, "system_name": string, "document_type": "HLD"|"LLD"|"Combined", ...},
      "high_level_design": {
          "components": [{"component_name": string, "description": string, "owner": string, "dependencies": [string]}],
          "integration_points": [{"source": string, "target": string, ...}],
          ...
      },
      "low_level_design": {
          "components": [...same shape as above...],
          ...
      }
    }
    """
    try:
        if not os.path.exists(path):
            logger.error(f"Design document JSON not found at {path}")
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load design document JSON")
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


def _build_enriched_component_label(base_name: str, component: dict) -> str:
    """
    Build a multi-line label for a design-document component node.
    """
    lines = [base_name]

    owner = component.get("owner")
    if isinstance(owner, str) and owner.strip():
        lines.append(f"Owner: {owner.strip()}")

    tech_stack = component.get("technology_stack")
    if isinstance(tech_stack, list) and tech_stack:
        first = next((t for t in tech_stack if isinstance(t, str) and t.strip()), None)
        if first:
            lines.append(f"Tech: {first.strip()}")

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
#  EDGE INFERENCE -- PROCESS SCHEMA (GENERIC + HARD FALLBACK)
# ============================================================

def _infer_edges_from_process_json() -> Tuple[str | None, List[Tuple[str, str]], Dict[str, str], Dict[str, str]]:
    """
    Infer, from output/process_data.json:
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
#  EDGE INFERENCE -- DESIGN DOCUMENT SCHEMA (GENERIC + HARD FALLBACK)
# ============================================================

def _infer_edges_from_design_json() -> Tuple[str | None, List[Tuple[str, str]], Dict[str, str], Dict[str, str]]:
    """
    Infer, from output/design_data.json:
    - doc_name (from document_metadata.title or document_metadata.system_name)
    - edges: built from high_level_design.integration_points (source/target) plus each
      component's own 'dependencies' list (dependency -> component_name); falls back to
      low_level_design.components/integration_points when high_level_design has no
      components (e.g. an "LLD"-only document).
    - lane_map (component_name -> owner, defaulting to "Component")
    - label_map (component_name -> enriched_label)

    ALWAYS returns at least one edge.
    """
    data = _load_design_json()
    if not data or not isinstance(data, dict):
        logger.warning("No valid design document JSON; using fallback Start→End")
        return "design", [("Start", "End")], {"Start": "Component", "End": "Component"}, {"Start": "Start", "End": "End"}

    metadata = data.get("document_metadata") or {}
    doc_name = None
    if isinstance(metadata, dict):
        doc_name = metadata.get("title") or metadata.get("system_name")
    doc_name = doc_name or "design"

    hld = data.get("high_level_design") or {}
    lld = data.get("low_level_design") or {}

    raw_components = []
    integration_points = []
    if isinstance(hld, dict) and isinstance(hld.get("components"), list) and hld.get("components"):
        raw_components = hld.get("components")
        if isinstance(hld.get("integration_points"), list):
            integration_points = hld.get("integration_points")
    elif isinstance(lld, dict) and isinstance(lld.get("components"), list):
        raw_components = lld.get("components")
        # LLD has no integration_points field in the schema; dependencies[] still applies.

    if not isinstance(raw_components, list):
        raw_components = []

    valid_components: List[dict] = []
    for c in raw_components:
        if isinstance(c, dict):
            name = c.get("component_name")
            if isinstance(name, str) and name.strip():
                valid_components.append(c)
        elif isinstance(c, str) and c.strip():
            valid_components.append({"component_name": c.strip()})

    if not valid_components:
        logger.warning("No valid design components inferred; using fallback Start→End")
        return doc_name, [("Start", "End")], {"Start": "Component", "End": "Component"}, {"Start": "Start", "End": "End"}

    node_names: List[str] = []
    lane_map: Dict[str, str] = {}
    label_map: Dict[str, str] = {}
    for c in valid_components:
        raw_name = c.get("component_name")
        if not isinstance(raw_name, str):
            continue
        base_name = _normalize_node_label(raw_name)
        if not base_name:
            continue
        if base_name not in node_names:
            node_names.append(base_name)
        owner = c.get("owner")
        lane_map[base_name] = owner.strip() if isinstance(owner, str) and owner.strip() else "Component"
        label_map[base_name] = _build_enriched_component_label(base_name, c)

    edges: List[Tuple[str, str]] = []

    # 1) integration_points (source -> target), restricted to known component names.
    if isinstance(integration_points, list):
        for ip in integration_points:
            if not isinstance(ip, dict):
                continue
            source = ip.get("source")
            target = ip.get("target")
            if not (isinstance(source, str) and source.strip() and isinstance(target, str) and target.strip()):
                continue
            source_label = _normalize_node_label(source)
            target_label = _normalize_node_label(target)
            if source_label in node_names and target_label in node_names and source_label != target_label:
                edge = (source_label, target_label)
                if edge not in edges:
                    edges.append(edge)

    # 2) component-level dependencies (dependency -> component_name).
    for c in valid_components:
        this_name = c.get("component_name")
        if not isinstance(this_name, str) or not this_name.strip():
            continue
        this_label = _normalize_node_label(this_name)

        deps = c.get("dependencies") or []
        if not isinstance(deps, list):
            continue

        for dep in deps:
            if not isinstance(dep, str) or not dep.strip():
                continue
            dep_label = _normalize_node_label(dep)
            if dep_label in node_names and dep_label != this_label:
                edge = (dep_label, this_label)
                if edge not in edges:
                    edges.append(edge)

    # 3) Fallback when no explicit relationships were declared.
    if not edges:
        if len(node_names) == 1:
            only = node_names[0]
            edges = [("Start", only), (only, "End")]
            lane_map["Start"] = "Component"
            lane_map["End"] = "Component"
            label_map.setdefault("Start", "Start")
            label_map.setdefault("End", "End")
        else:
            logger.warning(
                "No integration_points/dependencies inferred between %d components; "
                "falling back to declaration-order chain", len(node_names)
            )
            for i in range(len(node_names) - 1):
                edges.append((node_names[i], node_names[i + 1]))

    if not edges:
        logger.warning("No edges inferred; using fallback Start→End")
        edges = [("Start", "End")]
        lane_map["Start"] = "Component"
        lane_map["End"] = "Component"
        label_map.setdefault("Start", "Start")
        label_map.setdefault("End", "End")

    return doc_name, edges, lane_map, label_map


# ============================================================
#  EDGE INFERENCE -- DISPATCHER (BOTH SCHEMAS)
# ============================================================

def _infer_edges_from_json() -> Tuple[str | None, List[Tuple[str, str]], Dict[str, str], Dict[str, str]]:
    """
    Schema-aware dispatcher. Picks between the process-schema and design-document-schema
    edge inference logic based on which normalized JSON file is actually on disk, so this
    single agent keeps generating BPMN-style swimlane diagrams for business processes exactly
    as it always has, AND generates architecture/component diagrams for HLD/LLD/Combined
    design documents, without the caller having to say which pipeline it's running in.

    Routing rule delegates to utils._detect_schema_type_from_disk(), the single shared
    file-existence check also used by load_master_process_json/load_process_template/
    load_full_process_context and doc_generation_agent.py, so this "which schema is active"
    decision lives in exactly one place rather than being duplicated per caller:
      - output/design_data.json exists AND output/process_data.json does NOT exist -> design
      - otherwise (process file exists, neither exists, or both exist) -> process (unchanged
        default behaviour, so the existing process pipeline is never affected by this change)
    """
    if _detect_schema_type_from_disk() == "design":
        return _infer_edges_from_design_json()

    return _infer_edges_from_process_json()


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
#  DIAGRAM GENERATION (ALWAYS PRODUCES SOMETHING, BOTH SCHEMAS)
# ============================================================

def generate_clean_diagram() -> str:
    """
    Generates a refined architecture diagram as a PNG image, for EITHER a business process
    (BPMN-style swimlane diagram, keyed by process_steps/responsible_party) or an
    architectural design document (component/integration diagram, keyed by
    high_level_design.components/integration_points), depending on which normalized JSON
    file is present in output/ -- see _infer_edges_from_json().

    This function restores circular node styles and the original color schema, retains
    swimlane/ownership-lane backgrounds for organizational clarity, and implements text
    wrapping for node labels to prevent clipping. The diagram is laid out with nodes grouped
    by lane, edges drawn with arrows, and nodes styled for readability. The output image is
    saved to 'output/<name>_flow.png'.
    Returns:
        str: A message indicating the success or failure of the diagram generation.
    """
    import textwrap
    logger.debug("Generating final diagram: Tidied Bisected Circle with visible Arrowheads...")

    try:
        # LOAD DATA (schema-aware: process or design document)
        is_design = _detect_schema_type_from_disk() == "design"

        result = _infer_edges_from_json()
        if not result:
            if is_design:
                return "ERROR: Could not infer edges. Ensure output/design_data.json exists."
            return "ERROR: Could not infer edges. Ensure output/process_data.json exists."

        inferred_name, inferred_edges, lane_map, label_map = result
        default_title = "System Architecture" if is_design else "Process Architecture"
        final_name = (inferred_name or default_title).strip()
        edges = inferred_edges or []

        G = nx.DiGraph()
        G.add_edges_from(edges)

        default_lane = "Component" if is_design else "Process"
        for n in G.nodes():
            lane_map.setdefault(n, default_lane)
            label_map.setdefault(n, n)

        # IDENTIFY START AND END (Logic-based)
        # Start = No incoming edges; End = No outgoing edges
        start_nodes = [n for n, d in G.in_degree() if d == 0]
        end_nodes = [n for n, d in G.out_degree() if d == 0]

        # 1. POSITIONING
        x_spacing, y_spacing = 5.0, -4.0
        nodes = list(G.nodes())
        lanes = sorted(list(set(lane_map.get(n, default_lane) for n in nodes)))
        lane_y_indices = {lane: idx for idx, lane in enumerate(lanes)}

        lane_positions = {lane: [] for lane in lanes}
        for n in nodes:
            lane = lane_map.get(n, default_lane)
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
        lane_colors = _get_lane_colormap(len(lanes))
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

        plt.title(f"{default_title}: {final_name}", fontsize=15, pad=30, fontweight='bold')
        plt.axis("off")

        logger.debug("Diagram generation complete. Saving output...")

        # 7. SAVE
        default_out_path = "output/design_flow.png" if is_design else "output/process_flow.png"
        out_path = default_out_path
        if final_name:
            out_path = f"output/{safe_filename_component(final_name.lower())}_flow.png"

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
from .agent_wrappers import ProcessAgent
edge_inference_agent = ProcessAgent(
    name="Edge_Inference_Agent",
    description="Triggers swimlane/architecture diagram generation for either a business process or an architectural design document, based only on the normalized JSON already on disk.",
    instruction_file="common/edge_inference_agent.txt",
    tools=[generate_clean_diagram],
)

# ============================================================
# __main__ TEST HARNESS (DIRECT EXECUTION WITHOUT LLM)
# ============================================================
if __name__ == "__main__":

    print("\n=== Edge Inference Agent – Direct Test Harness ===")
    if len(sys.argv) < 3:
        print("Usage: python edge_inference_agent.py <process|design> <path_to_json>")
        print("Example: python edge_inference_agent.py process sample.json")
        print("Example: python edge_inference_agent.py design sample_design.json")
        sys.exit(1)

    schema_arg = sys.argv[1].strip().lower()
    json_path = sys.argv[2]
    if schema_arg not in ("process", "design"):
        print(f"ERROR: First argument must be 'process' or 'design', got: {schema_arg}")
        sys.exit(1)
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
    target_path = "output/design_data.json" if schema_arg == "design" else "output/process_data.json"
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Loaded JSON and wrote to {target_path}")

    name, edges, lane_map, label_map = _infer_edges_from_json()
    print("\nInferred name:", name)
    print("Inferred edges:")
    for e in edges:
        print(" ", e)

    print("\nGenerating diagram...")
    result = generate_clean_diagram()
    print("\nDiagram saved to:", result)
    print("=== Done ===\n")
