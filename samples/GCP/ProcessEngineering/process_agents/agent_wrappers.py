# process_agents/agent_wrappers.py

from __future__ import annotations

import asyncio
import functools
import logging
import random
import re
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
#   modelRetryMaxDelaySeconds   -> float backoff cap      (default: 90)
#   modelRetryQuotaDelayCapSeconds -> float cap on a provider-supplied
#                                     retry delay (see below)  (default: 120)

RETRY_ENABLED = str(getProperty("modelRetryEnabled", default="true")).lower() not in (
    "false", "0", "no", "off"
)
RETRY_MAX_ATTEMPTS = int(getProperty("modelRetryMaxAttempts", default=5))
RETRY_BASE_DELAY_S = float(getProperty("modelRetryBaseDelaySeconds", default=2))
RETRY_MAX_DELAY_S = float(getProperty("modelRetryMaxDelaySeconds", default=90))
RETRY_QUOTA_DELAY_CAP_S = float(
    getProperty("modelRetryQuotaDelayCapSeconds", default=120)
)

# =====================================================================
# Model-call request timeout
# =====================================================================
# Without this, a stalled connection to the model provider (dropped
# packets, a wedged proxy, etc.) blocks that agent's turn forever — no
# exception is ever raised, so the retry wrapper above never gets a
# chance to run and the whole pipeline just hangs. Setting an explicit
# HTTP timeout turns a silent hang into a "timed out" exception, which
# _is_retryable_error() already recognizes (see _RETRYABLE_MESSAGE_MARKERS),
# so the call is retried with backoff instead of hanging indefinitely.
#
# This bounds a single model call's HTTP round trip, not an agent's overall
# turn — a LoopAgent review cycle or a multi-tool-call turn can still take
# much longer in total; each individual model call just gets its own budget.
#
# Tunable via config/env:
#   modelTimeoutSeconds -> float seconds, <= 0 disables  (default: 300)
MODEL_TIMEOUT_MS: Optional[int] = None
_model_timeout_s = float(getProperty("modelTimeoutSeconds", default=300))
if _model_timeout_s > 0:
    MODEL_TIMEOUT_MS = int(_model_timeout_s * 1000)

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

# 403 is *not* retryable in general (bad API key, missing IAM role, billing
# disabled — none of that fixes itself). The one exception: ADK's context
# cache manager only checks its own locally-tracked expiry/invocation-count
# before reusing a cache — it never confirms the cache still exists
# server-side — so a cache Gemini evicted early (quota pressure, TTL drift,
# etc.) surfaces as a plain 403 here, not a 429/5xx. That specific shape is
# transient: a retry against a request with no stale cache reference (see
# generate_content_async_with_retry below) succeeds normally.
_CACHE_EVICTED_MARKERS = ("cachedcontent",)


def _status_code_of(exc: BaseException) -> Optional[int]:
    for attr in ("code", "status_code", "http_status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    return None


def _is_cache_eviction_error(exc: BaseException) -> bool:
    if _status_code_of(exc) != 403:
        return False
    text = f" {exc} ".lower()
    return any(marker in text for marker in _CACHE_EVICTED_MARKERS)


def _is_retryable_error(exc: BaseException) -> bool:
    if _is_cache_eviction_error(exc):
        return True
    code = _status_code_of(exc)
    if code is not None:
        return code in _RETRYABLE_STATUS_CODES
    text = f" {exc} ".lower()
    return any(marker in text for marker in _RETRYABLE_MESSAGE_MARKERS)


def _safe_deep_copy(obj: Any) -> Any:
    """Best-effort `model_copy(deep=True)`; falls back to the original object
    for anything that isn't a pydantic model (e.g. a plain string, as tests
    pass) rather than raising."""
    copier = getattr(obj, "model_copy", None)
    if callable(copier):
        try:
            return copier(deep=True)
        except Exception:
            return obj
    return obj


# Gemini's 429 RESOURCE_EXHAUSTED tells us exactly how long the per-minute
# token quota needs to refill (a google.rpc.RetryInfo.retryDelay, e.g. "4s"
# or "26s") — both as a structured detail on google.genai.errors.APIError
# and restated in the message text ("Please retry in 4.15...s"). Blind
# exponential backoff can retry sooner than that (wasting an attempt against
# a quota that hasn't refilled yet) or needlessly later, so honor it when
# present instead of guessing.
_RETRY_DELAY_TEXT_PATTERN = re.compile(r"retry in\s+(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def _parse_duration_seconds(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.endswith("s"):
        try:
            return float(value[:-1])
        except ValueError:
            return None
    return None


def _server_retry_delay(exc: BaseException) -> Optional[float]:
    """Best-effort extraction of a provider-suggested retry delay, in
    seconds, from a 429's structured error details or its message text."""
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        try:
            for item in details.get("error", {}).get("details", []):
                if isinstance(item, dict) and "retryDelay" in item:
                    delay = _parse_duration_seconds(item["retryDelay"])
                    if delay is not None:
                        return delay
        except Exception:
            pass
    match = _RETRY_DELAY_TEXT_PATTERN.search(str(exc))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _backoff_delay(attempt: int, exc: Optional[BaseException] = None) -> float:
    """Delay before the next retry.

    When the provider tells us exactly how long to wait (see
    _server_retry_delay), honor that — plus a small safety margin, since
    retrying at the exact instant a quota window rolls over often still
    loses the race — capped at RETRY_QUOTA_DELAY_CAP_S. Otherwise fall back
    to exponential backoff with full jitter, capped at RETRY_MAX_DELAY_S.
    """
    if exc is not None:
        hint = _server_retry_delay(exc)
        if hint is not None:
            return min(hint + random.uniform(0.5, 2.0), RETRY_QUOTA_DELAY_CAP_S)
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
        # ADK's context-cache manager mutates llm_request in place before the
        # network call (strips system_instruction/tools, truncates contents,
        # points config.cached_content at a specific cache name). If that
        # call fails, naively retrying with the same object would resend a
        # request that's missing its own instructions/tools and is pinned to
        # whatever cache reference just failed. Snapshot the pristine request
        # once, up front, and retry from a fresh copy of *that* each time.
        pristine_request = _safe_deep_copy(llm_request)
        attempt = 0
        current_request = llm_request
        while True:
            yielded_any = False
            try:
                async for response in original_fn(current_request, stream=stream):
                    yielded_any = True
                    yield response
                return
            except Exception as exc:
                if yielded_any or attempt >= RETRY_MAX_ATTEMPTS or not _is_retryable_error(exc):
                    raise
                delay = _backoff_delay(attempt, exc)
                attempt += 1
                logger.warning(
                    "[%s] Transient model error (attempt %d/%d) — retrying in "
                    "%.1fs: %s",
                    model_name, attempt, RETRY_MAX_ATTEMPTS, delay, exc,
                )
                await asyncio.sleep(delay)
                current_request = _safe_deep_copy(pristine_request)
                if _is_cache_eviction_error(exc) and hasattr(current_request, "cache_metadata"):
                    # Drop the dead cache reference so this attempt sends the
                    # full request uncached instead of hitting the same
                    # already-rejected cache_name again.
                    current_request.cache_metadata = None

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


def _apply_default_timeout(
    gcc: Optional[types.GenerateContentConfig],
) -> Optional[types.GenerateContentConfig]:
    """Ensure `gcc.http_options.timeout` is set (see MODEL_TIMEOUT_MS above),
    without overriding a timeout the caller explicitly configured."""
    if MODEL_TIMEOUT_MS is None:
        return gcc
    if gcc is None:
        gcc = types.GenerateContentConfig()
    if gcc.http_options is None:
        gcc.http_options = types.HttpOptions(timeout=MODEL_TIMEOUT_MS)
    elif gcc.http_options.timeout is None:
        gcc.http_options.timeout = MODEL_TIMEOUT_MS
    return gcc


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
        resolved_gcc = _apply_default_timeout(resolved_gcc)
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

    # clone() is inherited from google.adk.agents.BaseAgent, which ADK's own
    # runtime relies on internally (e.g. sub-agent cloning, resume handling).
    # Do not override it here — a prior override with an incompatible
    # signature (`**overrides` instead of `update: Mapping`) broke ADK's
    # internal calls like `agent.clone(update={"rerun_on_resume": True})`.

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

    # clone() is inherited from google.adk.agents.BaseAgent — see the same
    # note on DefaultLlmAgent above. (google.adk.agents.Agent is literally
    # google.adk.agents.LlmAgent, so this class needs the identical fix.)

# Convenience factories
def ProcessLlmAgent(name: str, **overrides: Any) -> DefaultLlmAgent:
    return DefaultLlmAgent(name=name, **overrides)

def ProcessAgent(name: str, **overrides: Any) -> DefaultAgent:
    return DefaultAgent(name=name, **overrides)