import os

import pytest

from process_toolkit import paths
from process_toolkit.docgen.proposal_architecture_diagram import (
    _layered_component_positions,
    generate_proposal_architecture_diagram,
)

SAMPLE_COMPONENTS = [
    {"name": "Ingestion API", "description": "Receives documents.", "connects_to": ["OCR Engine"]},
    {"name": "OCR Engine", "description": "Extracts text.", "connects_to": ["RAG Engine"]},
    {"name": "RAG Engine", "description": "Answers queries.", "connects_to": ["SAP Integration"]},
    {"name": "SAP Integration", "description": "Writes structured data.", "connects_to": []},
]


def test_raises_when_no_usable_components():
    with pytest.raises(ValueError):
        generate_proposal_architecture_diagram([], "Vendor Portal")
    with pytest.raises(ValueError):
        generate_proposal_architecture_diagram([{"description": "no name"}], "Vendor Portal")


def test_generates_a_png_at_the_expected_path():
    out_path = generate_proposal_architecture_diagram(SAMPLE_COMPONENTS, "Vendor Portal")
    assert out_path == paths.output_path("vendor_portal_architecture.png")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0


def test_layered_positions_assigns_increasing_depth_along_the_chain():
    _, pos = _layered_component_positions(SAMPLE_COMPONENTS)
    # A linear chain -- each component's X coordinate should strictly
    # increase down the chain (BFS depth from the one root).
    xs = [pos[c["name"]][0] for c in SAMPLE_COMPONENTS]
    assert xs == sorted(xs)
    assert len(set(xs)) == len(xs)


def test_layered_positions_centers_siblings_at_the_same_depth():
    components = [
        {"name": "Root", "description": "", "connects_to": ["Left", "Right"]},
        {"name": "Left", "description": "", "connects_to": []},
        {"name": "Right", "description": "", "connects_to": []},
    ]
    _, pos = _layered_component_positions(components)
    assert pos["Left"][0] == pos["Right"][0]  # same depth -- same X
    assert pos["Left"][1] != pos["Right"][1]  # distinct Y -- not stacked
    # Centered around the root's own Y.
    assert pytest.approx(pos["Root"][1]) == (pos["Left"][1] + pos["Right"][1]) / 2


def test_layered_positions_handles_a_disconnected_component():
    components = [
        {"name": "A", "description": "", "connects_to": ["B"]},
        {"name": "B", "description": "", "connects_to": []},
        {"name": "Orphan", "description": "", "connects_to": []},
    ]
    graph, pos = _layered_component_positions(components)
    assert set(graph.nodes()) == {"A", "B", "Orphan"}
    assert "Orphan" in pos


def test_ignores_a_connects_to_target_that_is_not_a_real_component():
    components = [
        {"name": "A", "description": "", "connects_to": ["Nonexistent"]},
    ]
    graph, pos = _layered_component_positions(components)
    assert list(graph.edges()) == []
    assert "A" in pos
