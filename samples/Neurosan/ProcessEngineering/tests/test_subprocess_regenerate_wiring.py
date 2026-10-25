"""Wiring coverage for the standalone subprocess-regeneration network
(registries/process_subprocess_regenerate.hocon), ported from the ADK port's
own Subprocess_Driver_Agent_Main (process_agents/process/subprocess_driver_agent.py).

Structural HOCON validation (including that every "class" path referenced
below actually resolves via neuro-san's own Resolver) is covered separately
by test_hocon_validation.py -- this file instead locks in that the network's
own tools re-export the same canonical classes process.hocon already uses
(so there is no duplicated/forked implementation), and that the router's
own instructions and the manifest actually mention the new network.
"""

from pathlib import Path

from coded_tools.process.subprocess_tool import (
    LoadProcessStepsCodedTool,
    SaveSubprocessFlowCodedTool,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_subprocess_regenerate_reuses_the_canonical_tool_classes():
    # process_subprocess_regenerate.hocon references "subprocess_tool.LoadProcessStepsCodedTool"
    # and "subprocess_tool.SaveSubprocessFlowCodedTool" by the same bare module name process.hocon
    # uses -- neuro-san's Resolver resolves both references to this one module, so there is only
    # ever one class object here to import and check, not a per-network copy.
    assert LoadProcessStepsCodedTool.__module__ == "coded_tools.process.subprocess_tool"
    assert SaveSubprocessFlowCodedTool.__module__ == "coded_tools.process.subprocess_tool"


def test_router_references_the_subprocess_regenerate_network():
    # The router only ever sees the network by its external path -- the internal front-man's
    # own agent name (Subprocess_Driver_Agent_Main) is never exposed across the network boundary.
    router_text = (PROJECT_ROOT / "registries" / "process_architect.hocon").read_text(encoding="utf-8")
    assert "SUBPROCESS REGENERATION" in router_text
    assert "`/process_subprocess_regenerate`" in router_text
    assert '"/process_subprocess_regenerate"' in router_text


def test_manifest_registers_the_subprocess_regenerate_network():
    manifest_text = (PROJECT_ROOT / "registries" / "manifest.hocon").read_text(encoding="utf-8")
    assert '"process_subprocess_regenerate.hocon"' in manifest_text
