"""Shells out to `ns validate` for every network this port owns (not the
scaffolded example networks neuro-san-studio ships) -- catches a broken
HOCON file (bad "class" path, etc.) that a pure-Python unit test
wouldn't.

`ns validate` does NOT catch every real runtime bug, though -- see
test_every_tool_declares_at_least_one_property below for one it misses
entirely."""

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from neuro_san.internals.graph.persistence.agent_network_restorer import AgentNetworkRestorer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTED_NETWORKS = [
    "registries/requirements_summary.hocon",
    "registries/requirements_chunk_extractor.hocon",
    "registries/requirements_consultant.hocon",
    "registries/requirements_reviewer.hocon",
    "registries/requirements_simulation_query.hocon",
    "registries/requirements_doc_pipeline.hocon",
    "registries/proposal_response_pipeline.hocon",
    "registries/proposal_response_consultant.hocon",
    "registries/proposal_response_reviewer.hocon",
    "registries/cloudarch.hocon",
    "registries/process.hocon",
    "registries/process_import.hocon",
    "registries/process_consultant.hocon",
    "registries/process_scenario_tester.hocon",
    "registries/process_simulation_query.hocon",
    "registries/cloudarch_consultant.hocon",
    "registries/cloudarch_import.hocon",
    "registries/cloudarch_simulation_query.hocon",
    "registries/cloudarch_attack_simulation_query.hocon",
    "registries/cloudarch_finops.hocon",
    "registries/cloudarch_iac.hocon",
    "registries/process_update.hocon",
    "registries/design.hocon",
    "registries/design_import.hocon",
    "registries/design_update.hocon",
    "registries/design_consultant.hocon",
    "registries/design_scenario_tester.hocon",
    "registries/design_simulation_query.hocon",
    "registries/regenerate_document.hocon",
    "registries/process_subprocess_regenerate.hocon",
    "registries/process_architect.hocon",
]

_NS_EXECUTABLE = shutil.which("ns", path=str(PROJECT_ROOT / ".venv" / "bin")) or "ns"


@pytest.mark.parametrize("network_path", PORTED_NETWORKS)
def test_network_passes_structural_validation(network_path):
    result = subprocess.run(
        [_NS_EXECUTABLE, "validate", network_path],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60,
    )
    combined_output = result.stdout + result.stderr
    assert "Validation passed" in combined_output, combined_output


def _collect_tool_entries(tools: List[Any], entries: List[Dict[str, Any]]) -> None:
    for entry in tools or []:
        if not isinstance(entry, dict):
            continue
        entries.append(entry)
        nested_tools = entry.get("tools")
        if isinstance(nested_tools, list):
            _collect_tool_entries(nested_tools, entries)


def _tool_entries_for_network(network_path: str) -> List[Dict[str, Any]]:
    abs_path = str(PROJECT_ROOT / network_path)
    restorer = AgentNetworkRestorer(registry_dir=None)
    agent_network = restorer.restore(file_reference=abs_path)
    config: Dict[str, Any] = agent_network.get_config()
    tools = config.get("tools") if isinstance(config, dict) else None
    entries: List[Dict[str, Any]] = []
    _collect_tool_entries(tools if isinstance(tools, list) else [], entries)
    return entries


# Regression guard for a real production bug: `ns validate` (above) does
# NOT catch an explicitly-empty "parameters.properties": {} dict on a
# tool's own function definition -- it's structurally valid HOCON, so
# `ns validate` passes clean, but the live server rejects it the first
# time any agent actually tries to call that tool, with "Function for
# <tool> needs to have at least one argument dictionary in its
# properties." Confirmed directly: proposal_response_pipeline.hocon's own
# load_requirements_summary entry declared `"parameters": {"type":
# "object", "properties": {}}` (copied from a tool that genuinely takes
# an argument, with the argument then stripped out) where every other
# zero-argument CodedTool in this project (e.g.
# requirements_consultant.hocon's own load_requirements_summary) instead
# omits "parameters" entirely -- the correct way to declare "takes no
# meaningful arguments." The fix is structural (omit the key), not a
# wording change, so this test asserts the shape directly rather than
# just re-running `ns validate`, which cannot see this class of bug at
# all.
@pytest.mark.parametrize("network_path", PORTED_NETWORKS)
def test_every_tool_declares_at_least_one_property_or_omits_parameters(network_path):
    failures = []
    for entry in _tool_entries_for_network(network_path):
        function = entry.get("function")
        if not isinstance(function, dict):
            continue
        parameters = function.get("parameters")
        if parameters is None:
            continue  # correct zero-argument shape -- "parameters" omitted entirely
        properties = parameters.get("properties") if isinstance(parameters, dict) else None
        if isinstance(properties, dict) and not properties:
            failures.append(
                f"{entry.get('name', '<unnamed>')}: \"parameters\" is present with an empty "
                "\"properties\" dict -- omit \"parameters\" entirely for a zero-argument tool "
                "instead (an empty properties dict is accepted by `ns validate` but rejected by "
                "the live server the first time the tool is actually called)."
            )
    assert not failures, "\n".join(failures)


def test_process_architect_router_uses_a_lower_temperature_for_routing_decisions():
    # Confirmed production bug, observed repeatedly across multiple live test runs: the router
    # skipped a REQUIRED tool call for plain consultant Q&A and answered from its own memory of
    # earlier, unrelated conversation context instead (see this network's own "NEVER SYNTHESIZE A
    # TOOL'S RESULT YOURSELF" section and Rule 4f) -- two rounds of progressively stronger
    # instruction wording reduced but did not eliminate it (4/4 -> 2/4 -> 3/4 fabricated answers
    # across three reruns of the same test script). That pattern -- textual reinforcement not
    # producing a monotonic improvement -- points at a model sampling/creativity trait rather than
    # an instruction gap, so a lower temperature specifically on this network's own routing
    # decision is the next lever. Scoped to process_architect.hocon only (an ADDITIVE override, not
    # a replacement of the shared config/llm_config.hocon) so sibling pipelines that benefit from
    # some creative latitude in their own drafting/narrative stages are unaffected.
    restorer = AgentNetworkRestorer(registry_dir=None)
    agent_network = restorer.restore(
        file_reference=str(PROJECT_ROOT / "registries/process_architect.hocon")
    )
    config: Dict[str, Any] = agent_network.get_config()
    llm_config = config.get("llm_config")
    assert llm_config is not None
    assert llm_config.get("temperature") == 0.2
    # The override must merge additively -- confirm the shared config's own fields survived.
    assert llm_config.get("model_name") == "gemini-3-flash"
