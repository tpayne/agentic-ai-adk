import importlib
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_STUBBED_PREFIXES = (
    "google", "pydantic", "certifi", "requests", "urllib3",
    "yaml", "matplotlib", "networkx",
)


def _force_real_reimport():
    """Drop any stub modules other test files leave in sys.modules (see
    test_web_service.py for why) plus every process_agents module, so the
    next import is genuine rather than reusing a stale/stubbed copy."""
    for name in list(sys.modules):
        if name in _STUBBED_PREFIXES or name.split(".", 1)[0] in _STUBBED_PREFIXES:
            del sys.modules[name]
    for name in list(sys.modules):
        if name == "process_agents" or name.startswith("process_agents."):
            del sys.modules[name]


def _import_module(module_path: str):
    _force_real_reimport()
    os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")
    return importlib.import_module(module_path)


def _instruction_text(relative_path: str) -> str:
    path = os.path.join(ROOT, "instructions", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class RequirementsSummaryAgentWiringTest(unittest.TestCase):
    """
    Regression coverage for wiring load_requirements_summary into the
    consultant/scenario/simulation-query agents (the user-facing,
    on-demand agents that answer questions about an EXISTING process,
    design, or diagram) so they can check whether the thing they're
    describing actually fulfills a previously-saved requirements summary.

    Deliberately excludes the three pipeline-internal auto-revision gates
    (Compliance_Agent, Design_Architecture_Simulation_Agent,
    Simulation_Optimization_Agent) -- those run automatically mid-creation
    with no user turn to ask a fulfillment question against, so they were
    not wired up; a dedicated negative test below locks that boundary in.
    """

    def _assert_has_requirements_tool(self, module_path: str, agent_attr: str, instruction_rel_path: str):
        # _import_module forces a fresh reimport of every process_agents.*
        # module (see _force_real_reimport) -- importing load_requirements_summary
        # AFTER that, not before, so it resolves to the SAME freshly-reimported
        # utils module the target agent module itself imported from. Grabbing
        # it first would bind a function object from the previous import
        # generation, which plain-function identity/equality would never
        # consider equal to what's actually sitting in agent.tools.
        module = _import_module(module_path)
        from process_agents.common.utils import load_requirements_summary

        agent = getattr(module, agent_attr)
        self.assertIn(
            load_requirements_summary, agent.tools,
            f"{module_path}.{agent_attr} is missing load_requirements_summary in its tools list",
        )
        text = _instruction_text(instruction_rel_path)
        self.assertIn(
            "load_requirements_summary", text,
            f"{instruction_rel_path} does not mention load_requirements_summary",
        )

    def test_consultant_agent_process(self):
        self._assert_has_requirements_tool(
            "process_agents.process.consultant_agent", "consultant_agent",
            "process/consultant_agent.txt",
        )

    def test_design_consultant_agent(self):
        self._assert_has_requirements_tool(
            "process_agents.design.consultant_design_agent", "consultant_design_agent",
            "design/consultant_design_agent.txt",
        )

    def test_scenario_tester(self):
        self._assert_has_requirements_tool(
            "process_agents.process.scenario_agent", "scenario_tester_agent",
            "process/scenario_tester_agent.txt",
        )

    def test_design_scenario_tester(self):
        self._assert_has_requirements_tool(
            "process_agents.design.scenario_design_agent", "design_scenario_tester_agent",
            "design/design_scenario_tester_agent.txt",
        )

    def test_cloudarch_consultant_agent(self):
        self._assert_has_requirements_tool(
            "process_agents.cloudarch.cloudarch_consultant_agent", "consultant_cloudarch_agent",
            "cloudarch/cloudarch_consultant_agent.txt",
        )

    def test_cloudarch_simulation_query_agent(self):
        self._assert_has_requirements_tool(
            "process_agents.cloudarch.cloudarch_simulation_agent", "cloudarch_simulation_query_agent",
            "cloudarch/cloudarch_simulation_query_agent.txt",
        )

    def test_design_architecture_simulation_query_agent(self):
        self._assert_has_requirements_tool(
            "process_agents.design.design_simulation_agent", "design_simulation_query_agent",
            "design/design_simulation_query_agent.txt",
        )

    def test_simulation_optimization_query_agent(self):
        self._assert_has_requirements_tool(
            "process_agents.process.simulation_agent", "simulation_query_agent",
            "process/simulation_query_agent.txt",
        )

    def test_pipeline_internal_gates_are_deliberately_not_wired(self):
        """The automatic self-auditing gates have no user turn to check a
        fulfillment question against -- confirm they were NOT given the
        tool, so a future edit that accidentally adds it (or accidentally
        removes it from a query agent and leaves it only on the gate) gets
        caught."""
        # Each _import_module call forces a fresh reimport (see the comment
        # in _assert_has_requirements_tool above) -- load_requirements_summary
        # must be re-grabbed after each one, matching that same reimport
        # generation, or assertNotIn would trivially (and wrongly) pass
        # against a stale function object no matter what's really in .tools.
        design_sim_module = _import_module("process_agents.design.design_simulation_agent")
        from process_agents.common.utils import load_requirements_summary as design_sim_tool
        self.assertNotIn(
            design_sim_tool, design_sim_module.design_simulation_agent.tools,
            "Design_Architecture_Simulation_Agent (pipeline-internal gate) should not have "
            "load_requirements_summary -- only its _query_agent sibling should.",
        )

        process_sim_module = _import_module("process_agents.process.simulation_agent")
        from process_agents.common.utils import load_requirements_summary as process_sim_tool
        self.assertNotIn(
            process_sim_tool, process_sim_module.simulation_agent.tools,
            "Simulation_Optimization_Agent (pipeline-internal gate) should not have "
            "load_requirements_summary -- only its _query_agent sibling should.",
        )


if __name__ == "__main__":
    unittest.main()
