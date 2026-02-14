# process_agents/agent_wrappers.py

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Callable, List, Union

from google.adk.agents import LlmAgent, Agent
from google.genai import types

from .utils import (
    getProperty,
    load_instruction,
    review_messages,
    review_outputs,
)

# --- NEW: sentinel so callers can distinguish "use default" vs "None (disable)" ---
_DEFAULT = object()   # private unique marker


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

        resolved_model = model or getProperty("MODEL")

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

        resolved_model = model or getProperty("MODEL")

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
