"""Regression guard for a real production bug: `ns validate` (see
test_hocon_validation.py) does NOT catch a "class" reference that is
syntactically fine but resolves to the WRONG place on disk. Confirmed
directly against two networks built this session (process_subprocess_
regenerate.hocon, cloudarch_import.hocon) that both passed `ns validate`
clean while being genuinely broken at runtime -- the live server raised
"Could not find class ... under AGENT_TOOL_PATH 'coded_tools' ... in the
agent network '<name>'" the first time an agent actually tried to call
the tool.

Root cause, read directly from neuro-san's own
internals/graph/activations/abstract_class_activation.py
(AbstractClassActivation._attempt_resolve): for a flat (non-nested)
network name, EXACTLY TWO package candidates are ever tried for a
"class": "<module>.<ClassName>" reference --

    1. coded_tools.<network_name>.<module>   (the network's OWN directory)
    2. coded_tools.<module>                  (the bare AGENT_TOOL_PATH root)

NOT any other existing coded_tools/<other_network>/ subdirectory, no
matter how genuinely shared the underlying implementation is. Every
network that reuses another network's own CodedTool class (process_import,
design_import, etc.) does so through a thin per-network shim file at
coded_tools/<this_network>/<module>.py that re-exports the real class --
this test reproduces that exact two-candidate algorithm for every
"class" reference in every network this port owns, so a new standalone
network that forgets its own shim fails HERE, at test time, instead of
on a live server mid-conversation.
"""

import importlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from neuro_san.internals.graph.persistence.agent_network_restorer import AgentNetworkRestorer

from tests.test_hocon_validation import PORTED_NETWORKS

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _collect_class_refs(tools: List[Any], refs: List[Tuple[str, str]]) -> None:
    """Recursively walks a network's "tools" list collecting every
    (tool_name, class_ref) pair, the same way cli.py's own
    _collect_agent_instructions walks it for a different purpose."""
    for entry in tools or []:
        if not isinstance(entry, dict):
            continue
        class_ref = entry.get("class")
        if isinstance(class_ref, str):
            refs.append((entry.get("name", "<unnamed>"), class_ref))
        nested_tools = entry.get("tools")
        if isinstance(nested_tools, list):
            _collect_class_refs(nested_tools, refs)


def _class_refs_for_network(network_path: str) -> List[Tuple[str, str]]:
    abs_path = str(PROJECT_ROOT / network_path)
    restorer = AgentNetworkRestorer(registry_dir=None)
    agent_network = restorer.restore(file_reference=abs_path)
    config: Dict[str, Any] = agent_network.get_config()
    tools = config.get("tools") if isinstance(config, dict) else None
    refs: List[Tuple[str, str]] = []
    _collect_class_refs(tools if isinstance(tools, list) else [], refs)
    return refs


def _network_name(network_path: str) -> str:
    return Path(network_path).stem


def _resolves(module_path: str, class_name: str) -> bool:
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        return False
    return hasattr(module, class_name)


# One parametrized case per network -- a network with no "class" references
# at all (a pure front-man referencing only other networks/already-covered
# tools) trivially passes with an empty list, same as test_hocon_validation.
@pytest.mark.parametrize("network_path", PORTED_NETWORKS)
def test_every_class_reference_resolves_the_way_the_live_server_resolves_it(network_path):
    network_name = _network_name(network_path)
    class_refs = _class_refs_for_network(network_path)

    failures = []
    for tool_name, class_ref in class_refs:
        module_name, _, class_name = class_ref.rpartition(".")
        if not module_name:
            failures.append(f"{tool_name}: malformed class ref {class_ref!r} (no module.Class split)")
            continue

        # The exact two candidates abstract_class_activation.py's own
        # _attempt_resolve tries for a flat (non-nested) network name.
        network_specific = f"coded_tools.{network_name}.{module_name}"
        global_root = f"coded_tools.{module_name}"

        if _resolves(network_specific, class_name) or _resolves(global_root, class_name):
            continue

        failures.append(
            f"{tool_name}: \"class\": \"{class_ref}\" does not resolve via either "
            f"{network_specific}.{class_name} or {global_root}.{class_name} -- "
            f"add a coded_tools/{network_name}/{module_name}.py shim re-exporting "
            f"the real class (see coded_tools/process_subprocess_regenerate/"
            f"subprocess_tool.py for the pattern), or move the canonical "
            f"implementation to coded_tools/{module_name}.py if it's meant to be "
            f"global."
        )

    assert not failures, "\n".join(failures)
