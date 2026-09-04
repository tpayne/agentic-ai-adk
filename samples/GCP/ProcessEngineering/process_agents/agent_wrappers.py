# process_agents/agent_wrappers.py

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Dict, Optional, Sequence, Callable, List, Union

from google.adk.agents import LlmAgent, Agent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from .utils import (
    getProperty,
    load_instruction,
    review_messages,
    review_outputs,
)

logger = logging.getLogger("ProcessArchitect.AgentWrappers")

# --- NEW: sentinel so callers can distinguish "use default" vs "None (disable)" ---
_DEFAULT = object()   # private unique marker


# =====================================================================
# Model-call retry / exponential backoff
# =====================================================================
# Every agent's model object gets wrapped here so a transient serving
# error (503 UNAVAILABLE "high demand", 429 RESOURCE_EXHAUSTED, dropped
# connections, etc.) is retried with exponential backoff *at the point
# of failure* — i.e. inside that one agent's model call — instead of
# propagating up and killing (and forcing a restart of) the whole
# SequentialAgent/LoopAgent pipeline. Because the retry happens below
# the pipeline layer, everything the pipeline already completed (prior
# stages, prior loop iterations, JSON already written to disk, etc.)
# is untouched — the failing agent's turn simply re-attempts itself and
# the pipeline proceeds as if nothing happened.
#
# Tunable via config/env (all optional):
#   modelRetryEnabled           -> "true"/"false"        (default: true)
#   modelRetryMaxAttempts       -> int retries per call   (default: 5)
#   modelRetryBaseDelaySeconds  -> float base backoff     (default: 2)
#   modelRetryMaxDelaySeconds   -> float backoff cap      (default: 60)

RETRY_ENABLED = str(getProperty("modelRetryEnabled", default="true")).lower() not in (
    "false", "0", "no", "off"
)
RETRY_MAX_ATTEMPTS = int(getProperty("modelRetryMaxAttempts", default=5))
RETRY_BASE_DELAY_S = float(getProperty("modelRetryBaseDelaySeconds", default=2))
RETRY_MAX_DELAY_S = float(getProperty("modelRetryMaxDelaySeconds", default=60))

# Status codes that are always safe to retry.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Substrings checked (case-insensitively) against str(exc) when no status
# code attribute is available, so provider-specific exception types (Gemini,
# LiteLLM/Anthropic/OpenAI/Bedrock wrappers, raw httpx/requests errors) are
# all caught uniformly.
_RETRYABLE_MESSAGE_MARKERS = (
    "unavailable",
    "resource_exhausted",
    "rate limit",
    "rate_limit",
    "overloaded",
    "high demand",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "service unavailable",
    " 503",
    " 429",
)


def _status_code_of(exc: BaseException) -> Optional[int]:
    for attr in ("code", "status_code", "http_status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    return None


def _is_retryable_error(exc: BaseException) -> bool:
    code = _status_code_of(exc)
    if code is not None:
        return code in _RETRYABLE_STATUS_CODES
    text = f" {exc} ".lower()
    return any(marker in text for marker in _RETRYABLE_MESSAGE_MARKERS)


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with full jitter, capped at RETRY_MAX_DELAY_S."""
    raw = RETRY_BASE_DELAY_S * (2 ** attempt)
    capped = min(raw, RETRY_MAX_DELAY_S)
    return random.uniform(0, capped)


def _wrap_with_retry(model_obj: Any, *, model_name: str) -> Any:
    """
    Monkey-patch `model_obj.generate_content_async` (an async generator)
    so transient errors are retried in place with exponential backoff.

    Safety rule: a retry is only attempted if the failing call has not
    already yielded any streamed content. If content was already yielded
    before the error, we re-raise rather than risk duplicating or
    corrupting partial output for that turn.
    """
    if not RETRY_ENABLED or model_obj is None:
        return model_obj

    original_fn = getattr(model_obj, "generate_content_async", None)
    if original_fn is None or getattr(original_fn, "_process_agent_retry_wrapped", False):
        # Nothing to wrap, or already wrapped (e.g. re-resolved via clone()).
        return model_obj

    @functools.wraps(original_fn)
    async def generate_content_async_with_retry(llm_request, stream: bool = False):
        attempt = 0
        while True:
            yielded_any = False
            try:
                async for response in original_fn(llm_request, stream=stream):
                    yielded_any = True
                    yield response
                return
            except Exception as exc:
                if yielded_any or attempt >= RETRY_MAX_ATTEMPTS or not _is_retryable_error(exc):
                    raise
                delay = _backoff_delay(attempt)
                attempt += 1
                logger.warning(
                    "[%s] Transient model error (attempt %d/%d) — retrying in "
                    "%.1fs: %s",
                    model_name, attempt, RETRY_MAX_ATTEMPTS, delay, exc,
                )
                await asyncio.sleep(delay)

    generate_content_async_with_retry._process_agent_retry_wrapped = True

    try:
        # Bypass pydantic's field-validating __setattr__ (BaseLlm subclasses
        # like Gemini/LiteLlm are pydantic models) so we can attach a plain
        # instance-level override of a method that isn't a declared field.
        object.__setattr__(model_obj, "generate_content_async", generate_content_async_with_retry)
    except Exception as exc:
        logger.warning(
            "Could not attach retry wrapper to model for '%s' (%s); "
            "continuing without automatic retry for this agent.",
            model_name, exc,
        )

    return model_obj


def _resolve_model(model: Optional[Any], *, _agent_name: str = "agent") -> Any:
    """
    Normalize a model spec into whatever ADK's LlmAgent/Agent expects, and
    transparently attach retry/backoff behaviour (see above) to whatever
    model object results.

    - None -> falls back to getProperty("MODEL")
    - Already a non-string model object (e.g. a LiteLlm instance, or any
      other BaseLlm) -> passed through as-is apart from the retry wrap, so
      clone() and callers who construct their own LiteLlm(...) never get
      double-wrapped (the wrapper is idempotent/guarded).
    - A provider-prefixed string, e.g. "anthropic/claude-sonnet-5",
      "openai/gpt-4o", "vertex_ai/claude-3-7-sonnet@20250219" -> wrapped
      in LiteLlm so non-Gemini providers work out of the box.
    - A bare Gemini model name, e.g. "gemini-2.5-flash" (no "/") -> built
      into a real `Gemini(...)` model object (rather than left as a plain
      string) so retry behaviour can be attached to it too; ADK accepts a
      BaseLlm instance here exactly as it accepts a bare model string.
    """
    resolved = model if model is not None else getProperty("MODEL")

    if resolved is None:
        return resolved

    if not isinstance(resolved, str):
        return _wrap_with_retry(resolved, model_name=_agent_name)

    if "/" in resolved:
        return _wrap_with_retry(LiteLlm(model=resolved), model_name=_agent_name)

    from google.adk.models import Gemini  # local import: avoids import cost/cycles when unused
    return _wrap_with_retry(Gemini(model=resolved), model_name=_agent_name)


# (unchanged) helper(s) ...
def _maybe_build_generate_config(
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
) -> Optional[types.GenerateContentConfig]:
    if temperature is None and top_p is None and top_k is None:
        return None
    return types.GenerateContentConfig(temperature=temperature, top_p=top_p, top_k=top_k)


SubAgentLike = Union[Any, Callable[[], Any]]

def _resolve_sub_agents(sub_agents: Optional[Sequence[SubAgentLike]]) -> Optional[List[Any]]:
    if sub_agents is None:
        return None
    resolved: List[Any] = []
    for sa in sub_agents:
        obj = sa() if callable(sa) else sa
        if obj is None:
            continue
        if isinstance(obj, (list, tuple)):
            for inner in obj:
                inner_obj = inner() if callable(inner) else inner
                if inner_obj is not None:
                    resolved.append(inner_obj)
        else:
            resolved.append(obj)
    return resolved


class DefaultLlmAgent(LlmAgent):
    def __init__(
        self,
        *,
        name: str,
        model: Optional[str] = None,
        description: Optional[str] = None,
        instruction: Optional[str] = None,
        instruction_file: Optional[str] = None,
        tools: Optional[Sequence[Any]] = None,
        sub_agents: Optional[Sequence[SubAgentLike]] = None,
        output_key: Optional[str] = None,
        include_contents: Optional[Sequence[Any]] = None,
        generate_content_config: Optional[types.GenerateContentConfig] = None,
        # quick knobs
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        # --- CHANGED: use sentinel defaults so you can pass None to disable ---
        before_model_callback: Any = _DEFAULT,
        after_model_callback: Any = _DEFAULT,
        **kwargs: Any,
    ) -> None:

        resolved_model = _resolve_model(model, _agent_name=name)

        if instruction is None and instruction_file:
            instruction = load_instruction(instruction_file)

        tools = list(tools) if tools is not None else []

        init_kwargs: Dict[str, Any] = {
            "name": name,
            "model": resolved_model,
            "instruction": instruction,
            "tools": tools,
        }

        if description is not None:
            init_kwargs["description"] = description

        resolved_subs = _resolve_sub_agents(sub_agents)
        if resolved_subs is not None:
            init_kwargs["sub_agents"] = resolved_subs

        if output_key is not None:
            init_kwargs["output_key"] = output_key
        if include_contents is not None:
            init_kwargs["include_contents"] = include_contents

        resolved_gcc = generate_content_config or _maybe_build_generate_config(
            temperature=temperature, top_p=top_p, top_k=top_k
        )
        if resolved_gcc is not None:
            init_kwargs["generate_content_config"] = resolved_gcc

        # --- NEW: only apply defaults if sentinel was not overridden ---
        if before_model_callback is _DEFAULT:
            init_kwargs["before_model_callback"] = review_messages
        else:
            init_kwargs["before_model_callback"] = before_model_callback

        if after_model_callback is _DEFAULT:
            init_kwargs["after_model_callback"] = review_outputs
        else:
            init_kwargs["after_model_callback"] = after_model_callback

        init_kwargs.update(kwargs)
        super().__init__(**init_kwargs)

    # --- clone() method ---
    # WARNING - Use this with caution! It does a shallow copy of tools and sub-agents, which may lead to shared
    # mutable state if those contain mutable objects. Always review the resulting agent's tools and sub-agents 
    # to ensure they are correctly isolated or shared as intended.
    # It may also corrupt callbacks if they reference mutable state. This is intended as a convenience for
    # quickly creating similar agents.
    def clone(self, **overrides: Any) -> "DefaultLlmAgent":
        params = {
            "name": self.name,
            "model": self.model,
            "description": self.description,
            "instruction": self.instruction,
            "tools": None,
            "sub_agents": None,
            "output_key": self.output_key,
            "include_contents": self.include_contents,
            "generate_content_config": self.generate_content_config,
            "before_model_callback": self.before_model_callback,
            "after_model_callback": self.after_model_callback,
        }

        params.update(overrides)
        new_agent = self.__class__(**params)
        new_agent.tools = list(self.tools) if self.tools else []
        return new_agent

class DefaultAgent(Agent):
    def __init__(
        self,
        *,
        name: str,
        model: Optional[str] = None,
        description: Optional[str] = None,
        instruction: Optional[str] = None,
        instruction_file: Optional[str] = None,
        tools: Optional[Sequence[Any]] = None,
        sub_agents: Optional[Sequence[SubAgentLike]] = None,
        output_key: Optional[str] = None,
        include_contents: Optional[Sequence[Any]] = None,
        generate_content_config: Optional[types.GenerateContentConfig] = None,
        # --- CHANGED: sentinel defaults here too ---
        before_model_callback: Any = _DEFAULT,
        after_model_callback: Any = _DEFAULT,
        **kwargs: Any,
    ) -> None:

        resolved_model = _resolve_model(model, _agent_name=name)

        if instruction is None and instruction_file:
            instruction = load_instruction(instruction_file)

        tools = list(tools) if tools is not None else []

        init_kwargs: Dict[str, Any] = {
            "name": name,
            "model": resolved_model,
            "instruction": instruction,
            "tools": tools,
        }

        if description is not None:
            init_kwargs["description"] = description

        resolved_subs = _resolve_sub_agents(sub_agents)
        if resolved_subs is not None:
            init_kwargs["sub_agents"] = resolved_subs

        if output_key is not None:
            init_kwargs["output_key"] = output_key
        if include_contents is not None:
            init_kwargs["include_contents"] = include_contents
        if generate_content_config is not None:
            init_kwargs["generate_content_config"] = generate_content_config

        if before_model_callback is _DEFAULT:
            init_kwargs["before_model_callback"] = review_messages
        else:
            init_kwargs["before_model_callback"] = before_model_callback

        if after_model_callback is _DEFAULT:
            init_kwargs["after_model_callback"] = review_outputs
        else:
            init_kwargs["after_model_callback"] = after_model_callback

        init_kwargs.update(kwargs)
        super().__init__(**init_kwargs)

    # --- clone() method ---
    # WARNING - Use this with caution! It does a shallow copy of tools and sub-agents, which may lead to shared
    # mutable state if those contain mutable objects. Always review the resulting agent's tools and sub-agents 
    # to ensure they are correctly isolated or shared as intended.
    # It may also corrupt callbacks if they reference mutable state. This is intended as a convenience for
    # quickly creating similar agents.
    def clone(self, **overrides: Any) -> "DefaultAgent":
        params = {
            "name": self.name,
            "model": self.model,
            "description": self.description,
            "instruction": self.instruction,
            "tools": None,
            "sub_agents": None,
            "output_key": self.output_key,
            "include_contents": self.include_contents,
            "generate_content_config": self.generate_content_config,
            "before_model_callback": self.before_model_callback,
            "after_model_callback": self.after_model_callback,
        }

        params.update(overrides)
        new_agent = self.__class__(**params)
        new_agent.tools = list(self.tools) if self.tools else []
        return new_agent

# Convenience factories
def ProcessLlmAgent(name: str, **overrides: Any) -> DefaultLlmAgent:
    return DefaultLlmAgent(name=name, **overrides)

def ProcessAgent(name: str, **overrides: Any) -> DefaultAgent:
    return DefaultAgent(name=name, **overrides)