import json
import sys
import types
import unittest
from unittest.mock import Mock, patch


def _install_dependency_stubs():
    if "yaml" not in sys.modules:
        yaml = types.ModuleType("yaml")
        yaml.safe_load = lambda stream: {}
        sys.modules["yaml"] = yaml

    if "certifi" not in sys.modules:
        certifi = types.ModuleType("certifi")
        certifi.where = lambda: "/etc/ssl/cert.pem"
        sys.modules["certifi"] = certifi

    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")
        adapters = types.ModuleType("requests.adapters")

        class HTTPAdapter:
            def __init__(self, *args, **kwargs):
                pass

            def sleep(self, sleep_time):
                return None

        class SSLError(Exception):
            pass

        requests.Session = lambda: None
        requests.exceptions = types.SimpleNamespace(SSLError=SSLError)
        adapters.HTTPAdapter = HTTPAdapter
        requests.adapters = adapters
        sys.modules["requests"] = requests
        sys.modules["requests.adapters"] = adapters

    if "urllib3" not in sys.modules:
        urllib3 = types.ModuleType("urllib3")
        urllib3_util = types.ModuleType("urllib3.util")
        retry_module = types.ModuleType("urllib3.util.retry")

        class Retry:
            def __init__(self, **kwargs):
                self.options = kwargs

        retry_module.Retry = Retry
        urllib3.util = urllib3_util
        urllib3_util.retry = retry_module
        sys.modules["urllib3"] = urllib3
        sys.modules["urllib3.util"] = urllib3_util
        sys.modules["urllib3.util.retry"] = retry_module

    google = sys.modules.setdefault("google", types.ModuleType("google"))
    adk = sys.modules.setdefault("google.adk", types.ModuleType("google.adk"))
    models = sys.modules.setdefault(
        "google.adk.models", types.ModuleType("google.adk.models")
    )
    agents = sys.modules.setdefault(
        "google.adk.agents", types.ModuleType("google.adk.agents")
    )
    callback_context = sys.modules.setdefault(
        "google.adk.agents.callback_context",
        types.ModuleType("google.adk.agents.callback_context"),
    )
    tools = sys.modules.setdefault(
        "google.adk.tools", types.ModuleType("google.adk.tools")
    )
    models_lite_llm = sys.modules.setdefault(
        "google.adk.models.lite_llm", types.ModuleType("google.adk.models.lite_llm")
    )
    tool_context = sys.modules.setdefault(
        "google.adk.tools.tool_context",
        types.ModuleType("google.adk.tools.tool_context"),
    )
    genai = sys.modules.setdefault("google.genai", types.ModuleType("google.genai"))

    class LlmAgent:
        def __init__(self, *args, **kwargs):
            pass

    class Agent(LlmAgent):
        pass

    class LiteLlm:
        def __init__(self, *args, **kwargs):
            pass

    class ToolContext:
        pass

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    models.LlmRequest = type("LlmRequest", (), {})
    models.LlmResponse = type("LlmResponse", (), {})
    class Gemini:
        def __init__(self, *args, **kwargs):
            pass

    models.Gemini = Gemini
    callback_context.CallbackContext = type("CallbackContext", (), {})
    agents.LlmAgent = LlmAgent
    agents.Agent = Agent
    models_lite_llm.LiteLlm = LiteLlm
    tool_context.ToolContext = ToolContext
    genai.types = types.SimpleNamespace(GenerateContentConfig=GenerateContentConfig)
    adk.agents = agents
    agents.callback_context = callback_context
    adk.models = models
    models.lite_llm = models_lite_llm
    adk.tools = tools
    tools.tool_context = tool_context
    google.adk = adk


_install_dependency_stubs()
from process_agents import grounding_agent  # noqa: E402


class GroundingValidationTests(unittest.TestCase):
    def test_path_matching_supports_openapi_parameters(self):
        self.assertTrue(
            grounding_agent._path_matches_openapi_template(
                "/users/{user_id}", "/users/123"
            )
        )
        self.assertFalse(
            grounding_agent._path_matches_openapi_template(
                "/users/{user_id}", "/users/123/profile"
            )
        )

    def test_endpoint_validation_checks_method_and_path(self):
        spec = {"paths": {"/users/{user_id}": {"get": {}, "delete": {}}}}
        self.assertTrue(
            grounding_agent._validate_requested_endpoint(spec, "GET", "/users/123")
        )
        self.assertFalse(
            grounding_agent._validate_requested_endpoint(spec, "POST", "/users/123")
        )

    def test_base_url_requires_http_or_https_server(self):
        self.assertEqual(
            grounding_agent._resolve_spec_base_url(
                {"servers": [{"url": "https://api.example.test/v1/"}]}
            ),
            "https://api.example.test/v1",
        )
        self.assertIsNone(
            grounding_agent._resolve_spec_base_url(
                {"servers": [{"url": "file:///tmp/api"}]}
            )
        )

    def test_perform_call_rejects_endpoint_not_in_spec_before_network(self):
        spec = {
            "servers": [{"url": "https://api.example.test"}],
            "paths": {"/health": {"get": {}}},
        }
        with patch.object(grounding_agent, "load_openapi", return_value=spec), patch.object(
            grounding_agent, "_build_session"
        ) as build_session:
            result = grounding_agent.perform_openapi_call(
                None, json.dumps({"method": "GET", "path": "/admin"})
            )
        self.assertFalse(result["ok"])
        self.assertIn("not allowed", result["error"])
        build_session.assert_not_called()

    def test_perform_call_uses_verified_request_for_allowed_endpoint(self):
        spec = {
            "servers": [{"url": "https://api.example.test/v1"}],
            "paths": {"/health": {"get": {}}},
        }
        response = Mock()
        response.json.return_value = {"status": "ok"}
        response.raise_for_status.return_value = None
        response.is_redirect = False
        response.is_permanent_redirect = False
        response.status_code = 200
        response.headers = {}
        session = Mock()
        session.get.return_value = response
        with patch.object(grounding_agent, "load_openapi", return_value=spec), patch.object(
            grounding_agent, "_build_session", return_value=session
        ), patch.object(grounding_agent, "getProperty", side_effect=lambda key, **kwargs: 0):
            result = grounding_agent.perform_openapi_call(
                None, json.dumps({"method": "GET", "path": "/health"})
            )

        self.assertEqual(result, {"ok": True, "data": {"status": "ok"}})
        session.get.assert_called_once()
        self.assertNotEqual(session.get.call_args.kwargs["verify"], False)


if __name__ == "__main__":
    unittest.main()
