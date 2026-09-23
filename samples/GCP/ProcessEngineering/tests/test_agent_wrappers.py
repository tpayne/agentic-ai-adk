import unittest
import asyncio
from unittest.mock import patch

from test_grounding_agent import _install_dependency_stubs

_install_dependency_stubs()
from process_agents import agent_wrappers  # noqa: E402


class RetryHelperTests(unittest.TestCase):
    def test_status_code_and_retryable_detection(self):
        error = RuntimeError("service unavailable")
        error.status_code = 503
        self.assertEqual(agent_wrappers._status_code_of(error), 503)
        self.assertTrue(agent_wrappers._is_retryable_error(error))
        self.assertFalse(agent_wrappers._is_retryable_error(ValueError("bad input")))

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
