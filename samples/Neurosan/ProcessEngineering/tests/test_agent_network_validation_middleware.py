"""Regression tests for the agent-network validation middleware classes --
previously uncovered entirely (see the code review that added this file).

AgentNetworkStructureValidationMiddleware.validate() pulls in
GetSubnetwork/GetMcpTool/GetToolbox's process-wide caches (file/manifest
reads) and is deliberately NOT exercised end-to-end here -- only its pure,
dependency-free methods are. AgentNetworkInstructionsValidationMiddleware's
validate() has no such dependency (KeywordNetworkValidator works purely off
the dict it's given), so it is tested end-to-end.
"""

import asyncio
from typing import Any

from middleware.agent_network_designer.validation.agent_network_instructions_validation_middleware import (
    AgentNetworkInstructionsValidationMiddleware,
)
from middleware.agent_network_designer.validation.agent_network_structure_validation_middleware import (
    AgentNetworkStructureValidationMiddleware,
)
from middleware.agent_network_designer.validation.agent_network_validation_middleware import (
    AgentNetworkValidationMiddleware,
)
from coded_tools.agent_network_editor.constants import AGENT_NETWORK_DEFINITION


class _StubValidationMiddleware(AgentNetworkValidationMiddleware):
    """Minimal concrete subclass so the ABSTRACT base's own aafter_agent
    control flow (not any real validator) can be exercised directly."""

    def __init__(self, sly_data: dict[str, Any], errors: list[str]) -> None:
        super().__init__(sly_data)
        self._errors = errors
        self.validate_called_with: dict[str, Any] | None = None

    def no_network_error_message(self) -> str:
        return "no network found"

    def validation_label(self) -> str:
        return "Stub"

    async def validate(self, network_def: dict[str, Any]) -> list[str]:
        self.validate_called_with = network_def
        return self._errors

    def format_error(self, error_list: list[str]) -> str:
        return "ERRORS: " + ", ".join(error_list)


class TestValidationMiddlewareBaseAfterAgent:
    """AgentNetworkValidationMiddleware.aafter_agent -- the shared
    no-network / errors-found / all-clear branches every subclass relies on."""

    def test_no_network_definition_jumps_to_model_with_no_network_message(self):
        mw = _StubValidationMiddleware({}, errors=[])
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result["jump_to"] == "model"
        assert result["messages"][0].content == "no network found"
        # validate() must not even be called when there's nothing to validate.
        assert mw.validate_called_with is None

    def test_validation_errors_jump_to_model_with_formatted_message(self):
        network_def = {"a": {"instructions": ""}}
        mw = _StubValidationMiddleware({AGENT_NETWORK_DEFINITION: network_def}, errors=["bad thing"])
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result["jump_to"] == "model"
        assert result["messages"][0].content == "ERRORS: bad thing"
        assert mw.validate_called_with == network_def

    def test_no_errors_returns_none(self):
        network_def = {"a": {"instructions": "fine", "description": "fine"}}
        mw = _StubValidationMiddleware({AGENT_NETWORK_DEFINITION: network_def}, errors=[])
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result is None

    def test_falsy_but_present_network_definition_is_treated_as_no_network(self):
        mw = _StubValidationMiddleware({AGENT_NETWORK_DEFINITION: {}}, errors=[])
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result["messages"][0].content == "no network found"


class TestInstructionsValidationMiddleware:
    """AgentNetworkInstructionsValidationMiddleware -- end to end, since its
    validate() has no external dependency beyond the dict it's handed."""

    def test_messages_and_labels(self):
        mw = AgentNetworkInstructionsValidationMiddleware({})
        assert "Cannot edit or create instructions" in mw.no_network_error_message()
        assert mw.validation_label() == "Instructions/Description"
        assert mw.format_error(["x", "y"]) == "Error(s):\nx\ny"

    def test_valid_network_has_no_errors(self):
        mw = AgentNetworkInstructionsValidationMiddleware({})
        network_def = {"a": {"instructions": "Be helpful.", "description": "Helps with things."}}
        errors = asyncio.run(mw.validate(network_def))
        assert errors == []

    def test_empty_instructions_is_an_error(self):
        mw = AgentNetworkInstructionsValidationMiddleware({})
        network_def = {"a": {"instructions": "   ", "description": "Helps with things."}}
        errors = asyncio.run(mw.validate(network_def))
        assert any("instructions" in e and "empty" in e for e in errors)

    def test_empty_description_is_an_error(self):
        mw = AgentNetworkInstructionsValidationMiddleware({})
        network_def = {"a": {"instructions": "Be helpful.", "description": ""}}
        errors = asyncio.run(mw.validate(network_def))
        assert any("description" in e and "empty" in e for e in errors)

    def test_missing_keys_entirely_are_not_errors(self):
        # Absent is different from empty -- an agent with neither key set
        # yet (e.g. mid-edit) must not be flagged the same as one with an
        # explicit blank value.
        mw = AgentNetworkInstructionsValidationMiddleware({})
        errors = asyncio.run(mw.validate({"a": {}}))
        assert errors == []


class TestStructureValidationMiddlewareLabels:
    """AgentNetworkStructureValidationMiddleware -- only the pure, cheap
    methods; validate() depends on GetSubnetwork/GetMcpTool/GetToolbox's
    process-wide caches and is out of scope here."""

    def test_messages_and_labels(self):
        mw = AgentNetworkStructureValidationMiddleware({})
        assert "create_new_network" in mw.no_network_error_message()
        assert mw.validation_label() == "Structure"

    def test_format_error(self):
        mw = AgentNetworkStructureValidationMiddleware({})
        formatted = mw.format_error(["bad edge", "missing agent"])
        assert "- bad edge" in formatted
        assert "- missing agent" in formatted
        assert "Use your tools to fix the errors." in formatted
