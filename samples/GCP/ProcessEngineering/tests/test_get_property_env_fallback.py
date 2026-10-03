import os
import sys
import types
import unittest
from unittest.mock import patch


def _install_google_stubs():
    """Make the utility module importable without installing the ADK runtime."""
    if "google.adk.models" in sys.modules:
        return

    google = types.ModuleType("google")
    adk = types.ModuleType("google.adk")
    models = types.ModuleType("google.adk.models")
    agents = types.ModuleType("google.adk.agents")
    callback_context = types.ModuleType("google.adk.agents.callback_context")
    tools = types.ModuleType("google.adk.tools")
    tool_context = types.ModuleType("google.adk.tools.tool_context")

    class LlmRequest:
        pass

    class LlmResponse:
        pass

    class CallbackContext:
        pass

    class ToolContext:
        pass

    models.LlmRequest = LlmRequest
    models.LlmResponse = LlmResponse
    callback_context.CallbackContext = CallbackContext
    tool_context.ToolContext = ToolContext
    agents.callback_context = callback_context
    tools.tool_context = tool_context
    adk.models = models
    adk.agents = agents
    adk.tools = tools
    google.adk = adk

    sys.modules.update(
        {
            "google": google,
            "google.adk": adk,
            "google.adk.models": models,
            "google.adk.agents": agents,
            "google.adk.agents.callback_context": callback_context,
            "google.adk.tools": tools,
            "google.adk.tools.tool_context": tool_context,
        }
    )


_install_google_stubs()
from process_agents.common import utils  # noqa: E402


class GetPropertyEnvFallbackTests(unittest.TestCase):
    """Regression test for a review finding: agent.py's web-service
    messages tell operators to configure the shared secret via a
    'WEBAPIKEY env var', but getProperty's environment fallback used to do
    a case-sensitive os.getenv(prop) lookup -- since the property itself is
    named "webApiKey" (mixed case), an exported WEBAPIKEY never matched, so
    the documented env var silently did nothing. getProperty now also tries
    an uppercased version of the property name."""

    def setUp(self):
        # Use patch.object (not direct attribute assignment) for both, so
        # whatever the real module state was before this test -- including
        # an already-cached properties file parsed by an earlier test in
        # the same process -- is restored afterward instead of leaking into
        # later tests that share this same imported utils module.
        self.properties_file_patch = patch.object(
            utils, "PROPERTIES_FILE",
            os.path.join("/nonexistent-for-this-test", "properties", "agentapp.properties"),
        )
        self.properties_file_patch.start()
        self.addCleanup(self.properties_file_patch.stop)

        self.cache_patch = patch.object(utils, "_CACHE", None)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    def test_uppercased_env_var_satisfies_a_mixed_case_property_name(self):
        with patch.dict(os.environ, {"WEBAPIKEY": "a-long-random-value"}, clear=False):
            self.assertEqual(utils.getProperty("webApiKey"), "a-long-random-value")

    def test_exact_case_env_var_still_works(self):
        with patch.dict(os.environ, {"webApiKey": "exact-case-value"}, clear=False):
            self.assertEqual(utils.getProperty("webApiKey"), "exact-case-value")

    def test_missing_property_and_env_var_returns_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("webApiKey", None)
            os.environ.pop("WEBAPIKEY", None)
            self.assertIsNone(utils.getProperty("webApiKey"))
            self.assertEqual(utils.getProperty("webApiKey", default="fallback"), "fallback")


if __name__ == "__main__":
    unittest.main()
