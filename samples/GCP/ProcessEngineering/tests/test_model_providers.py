import os
import unittest
from unittest.mock import patch

# Satisfy agent.py import-time credential check with a dummy key
os.environ.setdefault("GOOGLE_API_KEY", "dummy-import-key")
from process_agents.common.agent import configure_model_provider


class ConfigureModelProviderTests(unittest.TestCase):
    def test_gemini_without_keys_raises_environment_error(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(EnvironmentError) as ctx:
                configure_model_provider("gemini-3-flash-preview")
            self.assertIn("GOOGLE_API_KEY", str(ctx.exception))

    def test_gemini_with_api_key(self):
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "fake-key"}, clear=True):
            configure_model_provider("gemini-3-flash-preview")
            self.assertEqual(os.environ.get("ADK_MODEL_PROVIDER"), "api_key")

    def test_gemini_with_vertex_project(self):
        with patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "my-project"}, clear=True):
            configure_model_provider("gemini-3-flash-preview")
            self.assertEqual(os.environ.get("ADK_MODEL_PROVIDER"), "vertex")

    def test_ollama_chat_requires_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            configure_model_provider("ollama_chat/llama3.2")
            self.assertEqual(os.environ.get("ADK_MODEL_PROVIDER"), "ollama")

    def test_ollama_requires_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            configure_model_provider("ollama/mistral")
            self.assertEqual(os.environ.get("ADK_MODEL_PROVIDER"), "ollama")

    def test_openrouter_requires_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(EnvironmentError) as ctx:
                configure_model_provider("openrouter/openai/gpt-4o")
            self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-v1-test"}, clear=True):
            configure_model_provider("openrouter/openai/gpt-4o")
            self.assertEqual(os.environ.get("ADK_MODEL_PROVIDER"), "openrouter")

    def test_unrecognized_provider_prefix_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(EnvironmentError) as ctx:
                configure_model_provider("unknown_provider/some-model")
            self.assertIn("Unrecognized provider prefix", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
