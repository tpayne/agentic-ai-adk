"""Wiring coverage for the standalone subprocess-regeneration network
(registries/process_subprocess_regenerate.hocon), ported from the ADK port's
own Subprocess_Driver_Agent_Main (process_agents/process/subprocess_driver_agent.py).

`ns validate` (test_hocon_validation.py) checks HOCON structure but does
NOT catch a "class" reference that's syntactically fine yet resolves to
the wrong place on disk -- confirmed the hard way: this network originally
shipped with NO coded_tools/process_subprocess_regenerate/ shim directory
at all, passed `ns validate` clean, and then failed on the live server the
first time an agent actually tried to call load_process_steps ("Could not
find class ... under AGENT_TOOL_PATH 'coded_tools' ... in the agent
network 'process_subprocess_regenerate'"). test_coded_tool_class_
resolution.py now guards every network's every "class" reference against
this exact failure mode generically; the identity check below locks in
specifically that THIS network's own shim
(coded_tools/process_subprocess_regenerate/subprocess_tool.py) re-exports
process.hocon's own canonical classes rather than a forked copy.
"""

from pathlib import Path

from coded_tools.process.subprocess_tool import (
    LoadProcessStepsCodedTool as CanonicalLoadProcessSteps,
    SaveSubprocessFlowCodedTool as CanonicalSaveSubprocessFlow,
)
from coded_tools.process_subprocess_regenerate.subprocess_tool import (
    LoadProcessStepsCodedTool,
    SaveSubprocessFlowCodedTool,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_subprocess_regenerate_reuses_the_canonical_tool_classes():
    # Imported from the network's OWN shim path (coded_tools.
    # process_subprocess_regenerate.subprocess_tool) above -- the same
    # import neuro-san's own resolver performs at runtime -- and asserted
    # `is` (identity, not just equality) the canonical class, so a future
    # shim that accidentally forks/copies the implementation instead of
    # re-exporting it would fail this test too.
    assert LoadProcessStepsCodedTool is CanonicalLoadProcessSteps
    assert SaveSubprocessFlowCodedTool is CanonicalSaveSubprocessFlow


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
