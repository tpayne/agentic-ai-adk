"""Always-local re-export -- parse_drawio_graph is pure XML-string-in,
graph-dict-out, no disk I/O of its own, so it never needs to redirect even
though drawio/persistence.py (load/reset XML on disk -- a later phase) is
switchable."""

from process_toolkit.drawio.graph import parse_drawio_graph

__all__ = ["parse_drawio_graph"]
