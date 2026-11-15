"""Always-local re-export -- build_structured_drawio_xml takes structured
zone/component/edge data already in hand and returns an XML string; no
disk I/O of its own, unlike cloudarch/simulation.py|attack_simulation.py|
finops.py (a later phase), which fall back to loading the saved diagram
from disk and persist their results."""

from process_toolkit.cloudarch.layout import build_structured_drawio_xml

__all__ = ["build_structured_drawio_xml"]
