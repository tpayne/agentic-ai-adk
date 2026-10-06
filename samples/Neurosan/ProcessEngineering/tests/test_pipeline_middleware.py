"""Regression test for the five pipeline front-men's summarization
middleware (config/llm_config.hocon's "pipeline_middleware", referenced via
${pipeline_middleware} on each front-man) -- this project's equivalent of
the ADK original's events_compaction_config.

Catches two distinct ways this could silently break:
1. HOCON substitution regressing (a front-man losing its "middleware" key,
   or the shared block being malformed) -- caught by loading each network
   the same way `ns chat`/`ns run` do (AgentNetworkRestorer).
2. The middleware's own "model" string being unusable at construction time
   -- confirmed directly: a bare "gemini-3-flash" (no provider prefix)
   makes LangChain's init_chat_model() infer model_provider="google_vertexai"
   by default and fail importing a package this project doesn't install
   (langchain-google-vertexai), even though llm_config.hocon's actual model
   goes through the Gemini Developer API ("google_genai") via
   GOOGLE_API_KEY. The "google_genai:" prefix is required and is exactly
   the kind of detail a future edit could drop without anything else here
   catching it until a live run failed.
"""

import os

import pytest

os.environ.setdefault("AGENT_MANIFEST_FILE", os.path.join(os.getcwd(), "registries", "manifest.hocon"))
os.environ.setdefault("AGENT_TOOL_PATH", os.path.join(os.getcwd(), "coded_tools"))
os.environ["PYTHONPATH"] = os.getcwd()

from neuro_san.internals.graph.persistence.agent_network_restorer import AgentNetworkRestorer  # noqa: E402
from neuro_san.middleware.neuro_san_summarization_middleware import NeuroSanSummarizationMiddleware  # noqa: E402

_PIPELINE_NETWORKS = [
    "registries/process.hocon",
    "registries/process_update.hocon",
    "registries/design.hocon",
    "registries/design_update.hocon",
    "registries/cloudarch.hocon",
]


@pytest.fixture(autouse=True)
def _dummy_api_key(monkeypatch):
    # Middleware construction resolves/validates the underlying chat model
    # eagerly (see NeuroSanSummarizationMiddleware.__init__), which requires
    # SOME value here even though no real LLM call is ever made in this test.
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-a-real-credential")


@pytest.mark.parametrize("network_path", _PIPELINE_NETWORKS)
def test_pipeline_front_man_has_summarization_middleware_configured(network_path):
    network = AgentNetworkRestorer().restore(file_reference=network_path)
    front_man = network.get_config()["tools"][0]

    middleware = front_man.get("middleware")
    assert middleware, f"{front_man['name']} in {network_path} has no middleware configured"
    assert middleware[0]["class"] == (
        "neuro_san.middleware.neuro_san_summarization_middleware.NeuroSanSummarizationMiddleware"
    )


@pytest.mark.parametrize("network_path", _PIPELINE_NETWORKS)
def test_pipeline_middleware_args_actually_construct(network_path):
    network = AgentNetworkRestorer().restore(file_reference=network_path)
    front_man = network.get_config()["tools"][0]
    args = dict(front_man["middleware"][0]["args"])
    args["chat_history"] = []  # real HOCON value is `true`; a real list is needed to construct

    # Must not raise -- confirms the "model" string resolves to a real,
    # installed provider (not just that the HOCON key exists).
    NeuroSanSummarizationMiddleware(**args)
