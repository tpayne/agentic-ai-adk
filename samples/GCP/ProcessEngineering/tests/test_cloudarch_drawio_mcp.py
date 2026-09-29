import importlib
import os
import sys
import tempfile
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


def _import_cloudarch_agent_with_flag(enabled: bool):
    """Rewrites properties/agentapp.properties' enableDrawioShapeSearch line
    in a temp copy, points utils.PROPERTIES_FILE at it, and re-imports
    cloudarch_agent so module-level tool wiring picks up the new value."""
    real_props_path = os.path.join(ROOT, "properties", "agentapp.properties")
    with open(real_props_path) as f:
        content = f.read()
    replacement = "True" if enabled else "False"
    assert "enableDrawioShapeSearch" in content, (
        "properties/agentapp.properties no longer defines "
        "enableDrawioShapeSearch -- update this test's patch logic."
    )
    patched = "\n".join(
        f"enableDrawioShapeSearch = {replacement}" if line.strip().startswith("enableDrawioShapeSearch") else line
        for line in content.splitlines()
    )

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".properties", delete=False
    )
    tmp.write(patched)
    tmp.close()

    _force_real_reimport()
    os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")

    utils = importlib.import_module("process_agents.common.utils")
    utils.PROPERTIES_FILE = tmp.name
    utils._CACHE = None

    return importlib.import_module("process_agents.cloudarch.cloudarch_agent")


class CloudArchDrawioMcpToolTest(unittest.TestCase):
    """Covers the optional search_shapes tool (enableDrawioShapeSearch).

    Only tests conditional wiring at agent-construction time -- McpToolset
    doesn't connect to the MCP server (spawn `npx @drawio/mcp`) until its
    first get_tools() call, so building it here never launches a real
    process or touches the network.
    """

    def test_disabled_by_default_no_mcp_toolset(self):
        ca = _import_cloudarch_agent_with_flag(enabled=False)
        self.assertFalse(hasattr(ca, "_drawio_mcp_toolset"))
        self.assertNotIn(
            "McpToolset", [type(t).__name__ for t in ca._cloudarch_tools]
        )

    def test_enabled_adds_search_shapes_only_mcp_toolset(self):
        ca = _import_cloudarch_agent_with_flag(enabled=True)
        self.assertTrue(hasattr(ca, "_drawio_mcp_toolset"))
        toolset = ca._drawio_mcp_toolset
        self.assertEqual(toolset.tool_filter, ["search_shapes"])

        server_params = toolset.connection_params.server_params
        self.assertEqual(server_params.command, "npx")
        self.assertEqual(server_params.args, ["-y", "@drawio/mcp"])

        self.assertIn(toolset, ca._cloudarch_tools)


if __name__ == "__main__":
    unittest.main()
