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


class ImportAgentsWiringTest(unittest.TestCase):
    """
    Regression coverage for the two document-IMPORT agents (reads a
    directory of already-existing process/design source files and persists
    them directly into this toolkit's own JSON schema, distinct from the
    directory-context mode embedded in the create pipelines' analysis
    stages). Mirrors the neuro-san port's process_import.hocon/
    design_import.hocon networks.
    """

    def test_process_import_agent_tools_and_instructions(self):
        module = _import_module("process_agents.process.import_agent")
        from process_agents.common.utils import (
            load_directory_context,
            load_master_process_json,
            validate_process_json,
            persist_final_json,
        )

        agent = module.process_import_agent
        self.assertEqual(agent.name, "Process_Import_Agent")
        for tool in (load_directory_context, load_master_process_json, validate_process_json, persist_final_json):
            self.assertIn(
                tool, agent.tools,
                f"Process_Import_Agent is missing {tool.__name__} in its tools list",
            )

        text = _instruction_text("process/import_agent.txt")
        for name in ("load_directory_context", "load_master_process_json", "validate_process_json", "persist_final_json"):
            self.assertIn(name, text, f"process/import_agent.txt does not mention {name}")

    def test_design_import_agent_tools_and_instructions(self):
        module = _import_module("process_agents.design.import_agent")
        from process_agents.common.utils import (
            load_directory_context,
            load_master_design_json,
            validate_design_json,
            persist_final_design_json,
        )

        agent = module.design_import_agent
        self.assertEqual(agent.name, "Design_Import_Agent")
        for tool in (load_directory_context, load_master_design_json, validate_design_json, persist_final_design_json):
            self.assertIn(
                tool, agent.tools,
                f"Design_Import_Agent is missing {tool.__name__} in its tools list",
            )

        text = _instruction_text("design/import_agent.txt")
        for name in ("load_directory_context", "load_master_design_json", "validate_design_json", "persist_final_design_json"):
            self.assertIn(name, text, f"design/import_agent.txt does not mention {name}")

    def test_both_import_agents_are_registered_with_the_root_router(self):
        module = _import_module("process_agents.common.agent_registry")
        self.assertEqual(module.process_import_agent.name, "Process_Import_Agent")
        self.assertEqual(module.design_import_agent.name, "Design_Import_Agent")

        router_text = _instruction_text("common/agent.txt")
        self.assertIn("Process_Import_Agent", router_text)
        self.assertIn("Design_Import_Agent", router_text)


if __name__ == "__main__":
    unittest.main()
