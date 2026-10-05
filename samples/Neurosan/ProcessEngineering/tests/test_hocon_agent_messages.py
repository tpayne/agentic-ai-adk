"""Regression test for a real bug found while exercising this port against a
live LLM for the first time: when a front-man calls an internal LLM
sub-agent as a tool, neuro-san's BranchActivation.build() constructs that
sub-agent's triggering HumanMessage from (1) one sentence per declared
"function.parameters.properties" entry, filled from the caller's tool-call
arguments, and (2) an optional static "command" field on the agent's own
HOCON entry (see branch_activation.py). If a sub-agent has NEITHER --
every "reads its own state from disk/mailbox, no arguments needed" stage
agent in this port (Design_Agent, Compliance_Agent, Simulation_Agent,
CloudArch_Reviewer_Agent, Subprocess_Driver_Agent, ...) -- the resulting
HumanMessage is a literal empty string. Gemini's SDK rejects an all-empty
message list outright with "ValueError: contents are required.", after
LangChain's own empty-HumanMessage filtering strips it (other providers may
tolerate a system-prompt-only turn; Gemini does not). The fix is a
`"command"` field giving each such agent a short static kickoff string.

This test loads each network the same way `ns chat`/`ns run` do (via
AgentNetworkRestorer, not a text/regex scan) and replicates
BranchActivation's own assignments-string construction via the real
ArgumentAssigner, so it fails the exact same way neuro-san's real runtime
would for any INTERNAL (non-front-man) LLM sub-agent that regresses to
having neither a declared parameter nor a "command".
"""

import os

import pytest

os.environ.setdefault("AGENT_MANIFEST_FILE", os.path.join(os.getcwd(), "registries", "manifest.hocon"))
os.environ.setdefault("AGENT_TOOL_PATH", os.path.join(os.getcwd(), "coded_tools"))
os.environ["PYTHONPATH"] = os.getcwd()

from neuro_san.internals.graph.activations.argument_assigner import ArgumentAssigner  # noqa: E402
from neuro_san.internals.graph.persistence.agent_network_restorer import AgentNetworkRestorer  # noqa: E402

from tests.test_hocon_validation import PORTED_NETWORKS  # noqa: E402

# The front-man is always the first tool entry in the file (see every
# registry's own header comment) and is invoked via
# FrontManActivation.submit_message(user_input) with the real user/caller
# text directly (or, when called cross-network via "/name", through
# BranchActivation but with its own declared "inquiry" parameter populated
# by the caller) -- never through the empty-arguments path this test
# guards against. Every other "instructions"-bearing entry is an internal
# sub-agent this test must check.


@pytest.mark.parametrize("network_path", PORTED_NETWORKS)
def test_every_internal_sub_agent_gets_a_non_empty_triggering_message(network_path):
    network = AgentNetworkRestorer().restore(file_reference=network_path)
    tools = network.get_config()["tools"]
    front_man_name = tools[0]["name"]

    for spec in tools:
        name = spec["name"]
        if not spec.get("instructions") or name == front_man_name:
            continue  # not an internal LLM sub-agent (a CodedTool leaf, or the front-man itself)

        properties = ((spec.get("function") or {}).get("parameters") or {}).get("properties") or {}
        # Simulate a realistic call: a declared (and, in every case in this
        # port, required) property is always filled by the calling LLM --
        # testing with {} regardless of what's declared would falsely flag
        # a perfectly fine agent like Design_Doc_Update_Analyst (declares a
        # required "request" string) just because it also lacks "command",
        # which it doesn't need. Only an agent with NO declared properties
        # is actually called with {} in practice, since there's nothing for
        # the model to fill in.
        args = {key: "test value" for key in properties}
        assigner = ArgumentAssigner(properties)
        assignments_str = "\n".join(assigner.assign(args))
        command = spec.get("command")
        if command:
            assignments_str = f"{assignments_str}\n{command}"

        assert assignments_str.strip(), (
            f'"{name}" in {network_path} has no declared "function.parameters" and no "command" -- '
            'a caller invoking it with no arguments (the normal case for a "reads its own state" '
            'stage agent) would submit a literal empty HumanMessage, which Gemini rejects outright '
            'with "contents are required." Add a "command" field with a short static kickoff string.'
        )
