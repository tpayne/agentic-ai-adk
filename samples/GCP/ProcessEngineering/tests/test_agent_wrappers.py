import unittest
import asyncio
from unittest.mock import patch

from test_grounding_agent import _install_dependency_stubs

_install_dependency_stubs()
from process_agents.common import agent_wrappers  # noqa: E402


class CloneOverrideTests(unittest.TestCase):
    def test_wrapper_classes_do_not_override_clone(self):
        # google.adk.agents.BaseAgent.clone(update: Mapping) is called by
        # ADK's own runtime internals (sub-agent cloning, resume/rerun
        # handling — e.g. agent.clone(update={"rerun_on_resume": True})).
        # A wrapper-level `def clone(self, **overrides)` shadows that with
        # an incompatible signature and breaks those internal calls (this
        # happened twice: DefaultLlmAgent, then its sibling DefaultAgent).
        # Guard against reintroducing either by asserting neither class
        # defines its own `clone` — both must inherit it from BaseAgent.
        self.assertNotIn("clone", agent_wrappers.DefaultLlmAgent.__dict__)
        self.assertNotIn("clone", agent_wrappers.DefaultAgent.__dict__)


class RetryHelperTests(unittest.TestCase):
    def test_status_code_and_retryable_detection(self):
        error = RuntimeError("service unavailable")
        error.status_code = 503
        self.assertEqual(agent_wrappers._status_code_of(error), 503)
        self.assertTrue(agent_wrappers._is_retryable_error(error))
        self.assertFalse(agent_wrappers._is_retryable_error(ValueError("bad input")))

    def test_cache_eviction_403_is_retryable_but_other_403s_are_not(self):
        cache_error = RuntimeError("CachedContent not found (or permission denied)")
        cache_error.code = 403
        self.assertTrue(agent_wrappers._is_cache_eviction_error(cache_error))
        self.assertTrue(agent_wrappers._is_retryable_error(cache_error))

        auth_error = RuntimeError("PERMISSION_DENIED: missing IAM role")
        auth_error.code = 403
        self.assertFalse(agent_wrappers._is_cache_eviction_error(auth_error))
        self.assertFalse(agent_wrappers._is_retryable_error(auth_error))

    def test_backoff_honors_server_retry_delay_over_blind_exponential(self):
        # Gemini's 429 RESOURCE_EXHAUSTED names an exact quota refill delay
        # (google.rpc.RetryInfo.retryDelay). Blind exponential backoff can
        # retry before that window refills, wasting an attempt — so a
        # provided delay should win over the exponential guess, plus a small
        # margin, and stay within RETRY_QUOTA_DELAY_CAP_S.
        class QuotaError(Exception):
            code = 429
            details = {
                "error": {
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "4s",
                        }
                    ]
                }
            }

        with patch.object(agent_wrappers, "RETRY_QUOTA_DELAY_CAP_S", 120), patch.object(
            agent_wrappers.random, "uniform", side_effect=lambda low, high: low
        ):
            delay = agent_wrappers._backoff_delay(0, QuotaError())
        self.assertEqual(delay, 4.5)  # 4s hint + the 0.5s margin floor

        # message-text-only fallback (no structured `.details`)
        text_only_error = RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 23.8s.")
        text_only_error.code = 429
        self.assertEqual(agent_wrappers._server_retry_delay(text_only_error), 23.8)

        # no hint available at all -> falls back to plain exponential backoff
        self.assertIsNone(agent_wrappers._server_retry_delay(RuntimeError("boom")))

    def test_retry_after_cache_eviction_drops_dead_cache_reference(self):
        # Simulates ADK's own context-cache manager, which mutates
        # llm_request in place before the network call (strips
        # system_instruction, points cache_metadata at a cache_name) — see
        # gemini_context_cache_manager.py's _apply_cache_to_request. A retry
        # must not replay that mutated object, and must drop the dead
        # cache reference rather than reuse it.
        class FakeCacheMetadata:
            def __init__(self, cache_name):
                self.cache_name = cache_name

            def model_copy(self, deep=True):
                return FakeCacheMetadata(self.cache_name)

        class FakeRequest:
            def __init__(self):
                self.system_instruction = "be nice"
                self.cache_metadata = FakeCacheMetadata("cachedContents/dead-cache")

            def model_copy(self, deep=True):
                clone = FakeRequest()
                clone.system_instruction = self.system_instruction
                clone.cache_metadata = (
                    self.cache_metadata.model_copy(deep=True)
                    if self.cache_metadata is not None
                    else None
                )
                return clone

        class FakeModel:
            def __init__(self):
                self.seen = []

            async def generate_content_async(self, llm_request, stream=False):
                self.seen.append(
                    (
                        llm_request.system_instruction,
                        llm_request.cache_metadata.cache_name
                        if llm_request.cache_metadata
                        else None,
                    )
                )
                if len(self.seen) == 1:
                    # Simulate ADK stripping instructions once it commits to
                    # the (about to fail) cached_content reference.
                    llm_request.system_instruction = None
                    error = RuntimeError(
                        "CachedContent not found (or permission denied)"
                    )
                    error.code = 403
                    raise error
                yield "ok"

        with patch.object(agent_wrappers, "RETRY_MAX_ATTEMPTS", 2), patch.object(
            agent_wrappers, "RETRY_BASE_DELAY_S", 0
        ):
            model = FakeModel()
            wrapped = agent_wrappers._wrap_with_retry(model, model_name="test")

            async def collect():
                return [
                    item
                    async for item in wrapped.generate_content_async(FakeRequest())
                ]

            result = asyncio.run(collect())

        self.assertEqual(result, ["ok"])
        first_instruction, first_cache = model.seen[0]
        second_instruction, second_cache = model.seen[1]
        self.assertEqual(first_cache, "cachedContents/dead-cache")
        self.assertEqual(second_instruction, "be nice")
        self.assertIsNone(second_cache)

    def test_backoff_is_capped_and_nonnegative(self):
        with patch.object(agent_wrappers, "RETRY_BASE_DELAY_S", 2), patch.object(
            agent_wrappers, "RETRY_MAX_DELAY_S", 5
        ), patch.object(agent_wrappers.random, "uniform", side_effect=lambda low, high: high):
            self.assertEqual(agent_wrappers._backoff_delay(0), 2)
            self.assertEqual(agent_wrappers._backoff_delay(1), 4)
            self.assertEqual(agent_wrappers._backoff_delay(10), 5)

    def test_retry_wrapper_retries_transient_failure_then_returns(self):
        class Model:
            def __init__(self):
                self.calls = 0

            def generate_content(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("temporarily unavailable")
                return "ok"

        with patch.object(agent_wrappers, "RETRY_MAX_ATTEMPTS", 2), patch.object(
            agent_wrappers, "RETRY_BASE_DELAY_S", 0
        ):
            class AsyncModel(Model):
                async def generate_content_async(self, request, stream=False):
                    self.calls += 1
                    if self.calls == 1:
                        raise RuntimeError("temporarily unavailable")
                    yield "ok"

            async def collect():
                wrapped = agent_wrappers._wrap_with_retry(
                    AsyncModel(), model_name="test"
                )
                return [item async for item in wrapped.generate_content_async("prompt")]

            self.assertEqual(asyncio.run(collect()), ["ok"])

    def test_retry_wrapper_does_not_retry_permanent_failure(self):
        class Model:
            def generate_content(self, *args, **kwargs):
                raise ValueError("invalid request")

        class AsyncModel(Model):
            async def generate_content_async(self, request, stream=False):
                raise ValueError("invalid request")
                yield

        async def collect():
            wrapped = agent_wrappers._wrap_with_retry(
                AsyncModel(), model_name="test"
            )
            return [item async for item in wrapped.generate_content_async("prompt")]

        with self.assertRaises(ValueError):
            asyncio.run(collect())


class WrapperConfigurationTests(unittest.TestCase):
    def test_generate_config_is_only_built_for_supported_values(self):
        config = agent_wrappers._maybe_build_generate_config(
            temperature=0.2, top_p=0.9
        )
        self.assertIsNotNone(config)
        self.assertEqual(config.kwargs["temperature"], 0.2)
        self.assertIsNone(agent_wrappers._maybe_build_generate_config(None))

    def test_sub_agents_resolve_to_underlying_agent_objects(self):
        first = object()
        second = object()
        self.assertEqual(
            agent_wrappers._resolve_sub_agents([first, second]), [first, second]
        )
        self.assertIsNone(agent_wrappers._resolve_sub_agents(None))


if __name__ == "__main__":
    unittest.main()
