"""Regression tests for AgentNetworkPersistenceMiddleware -- previously
uncovered entirely (see the code review that added this file).

The full "validate successfully, then actually assemble+persist" path pulls
in HoconAgentNetworkAssembler/AgentNetworkPersistorFactory and the
GetSubnetwork/GetMcpTool process-wide caches, so aafter_agent's control flow
is tested with _validate_network/_assemble_and_persist monkeypatched to
isolate the glue this class itself is responsible for (retry counting,
jump_to routing, SKIP_DESIGNER reset, deploy-error vs success handling) from
those heavier collaborators. _assemble_and_persist's own front-man lookup
(the .pop()-on-empty-set crash this middleware was fixed for earlier in the
same review) is exercised directly, with only _create_persistor stubbed out
-- everything after the front-man lookup in that method is unreachable once
it raises, so nothing else needs stubbing for that one.
"""

import asyncio

import pytest

from coded_tools.agent_network_editor.constants import AGENT_NETWORK_DEFINITION
from coded_tools.agent_network_editor.constants import AGENT_NETWORK_NAME
from middleware.agent_network_designer.agent_network_definition_middleware import SKIP_DESIGNER
from middleware.agent_network_designer.persistence.agent_network_persistence_middleware import (
    AgentNetworkPersistenceMiddleware,
    DEFAULT_MAX_VALIDATION_ATTEMPTS,
)


def _middleware(sly_data=None):
    return AgentNetworkPersistenceMiddleware(reservationist=object(), sly_data=sly_data if sly_data is not None else {})


class TestConstructor:
    def test_default_max_validation_attempts(self, monkeypatch):
        monkeypatch.delenv("AGENT_NETWORK_DESIGNER_MAX_VALIDATION_ATTEMPTS", raising=False)
        mw = _middleware()
        assert mw.max_validation_attempts == DEFAULT_MAX_VALIDATION_ATTEMPTS

    def test_valid_env_override(self, monkeypatch):
        monkeypatch.setenv("AGENT_NETWORK_DESIGNER_MAX_VALIDATION_ATTEMPTS", "7")
        mw = _middleware()
        assert mw.max_validation_attempts == 7

    def test_invalid_env_value_falls_back_to_default(self, monkeypatch, caplog):
        monkeypatch.setenv("AGENT_NETWORK_DESIGNER_MAX_VALIDATION_ATTEMPTS", "not-a-number")
        with caplog.at_level("WARNING"):
            mw = _middleware()
        assert mw.max_validation_attempts == DEFAULT_MAX_VALIDATION_ATTEMPTS
        assert "not-a-number" in caplog.text

    def test_negative_env_value_is_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv("AGENT_NETWORK_DESIGNER_MAX_VALIDATION_ATTEMPTS", "-5")
        mw = _middleware()
        assert mw.max_validation_attempts == 0


class TestErrorResponse:
    def test_resets_skip_designer_to_false(self):
        mw = _middleware({SKIP_DESIGNER: True})
        result = mw._error_response("boom")
        assert mw.sly_data[SKIP_DESIGNER] is False
        assert result == {"messages": [result["messages"][0]], "jump_to": "model"}
        assert result["messages"][0].content == "boom"

    def test_leaves_skip_designer_alone_when_not_true(self):
        mw = _middleware({})
        mw._error_response("boom")
        assert SKIP_DESIGNER not in mw.sly_data


class TestDeployErrorResponse:
    def test_shape_has_no_jump_to(self):
        mw = _middleware()
        result = mw._deploy_error_response("network unreachable")
        assert "jump_to" not in result
        assert "could not be deployed" in result["messages"][0].content
        assert "network unreachable" in result["messages"][0].content


class TestAfterAgentGating:
    """aafter_agent's top-level gate: nothing happens without BOTH a
    network definition and a valid string name."""

    def test_no_network_definition_returns_none(self):
        mw = _middleware({AGENT_NETWORK_NAME: "my-net"})
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result is None

    def test_no_name_returns_none(self):
        mw = _middleware({AGENT_NETWORK_DEFINITION: {"a": {}}})
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result is None

    def test_non_string_name_returns_none(self):
        mw = _middleware({AGENT_NETWORK_DEFINITION: {"a": {}}, AGENT_NETWORK_NAME: 42})
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result is None


class TestAfterAgentValidationRetry:
    def _mw_with_errors(self, monkeypatch, structure_errors, instructions_errors):
        mw = _middleware({AGENT_NETWORK_DEFINITION: {"a": {}}, AGENT_NETWORK_NAME: "my-net"})

        async def _fake_validate_network(network_def):
            return structure_errors, instructions_errors

        monkeypatch.setattr(mw, "_validate_network", _fake_validate_network)
        return mw

    def test_errors_below_max_attempts_jumps_to_model_and_increments_counter(self, monkeypatch):
        mw = self._mw_with_errors(monkeypatch, ["bad edge"], [])
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result["jump_to"] == "model"
        assert "agent_network_editor" in result["messages"][0].content
        assert mw._validation_attempts == 1

    def test_both_kinds_of_errors_mention_both_tools_and_the_fix_order(self, monkeypatch):
        mw = self._mw_with_errors(monkeypatch, ["bad edge"], ["bad instructions"])
        result = asyncio.run(mw.aafter_agent(None, None))
        content = result["messages"][0].content
        assert "agent_network_editor" in content
        assert "agent_network_instructions_editor" in content
        assert "Fix the structural issues first" in content

    def test_reaching_max_attempts_ends_without_persisting(self, monkeypatch):
        mw = self._mw_with_errors(monkeypatch, ["bad edge"], [])
        mw.max_validation_attempts = 1
        mw._validation_attempts = 1
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result is None

    def test_validation_attempts_resets_after_a_clean_run(self, monkeypatch):
        mw = self._mw_with_errors(monkeypatch, ["bad edge"], [])
        mw._validation_attempts = 2
        asyncio.run(mw.aafter_agent(None, None))
        assert mw._validation_attempts == 3

        async def _clean(network_def):
            return [], []

        monkeypatch.setattr(mw, "_validate_network", _clean)

        async def _no_op_persist(network_def, agent_network_name, sample_queries):
            return None

        monkeypatch.setattr(mw, "_assemble_and_persist", _no_op_persist)
        monkeypatch.setattr(mw, "_determine_exported_network_definition", lambda *a, **k: None)
        asyncio.run(mw.aafter_agent(None, None))
        assert mw._validation_attempts == 0


class TestAfterAgentPersistOutcomes:
    """aafter_agent once validation is clean -- success vs. a reservations-
    mode deploy error, with _assemble_and_persist itself stubbed out."""

    def _mw_clean(self, monkeypatch, deploy_error):
        mw = _middleware({AGENT_NETWORK_DEFINITION: {"a": {}}, AGENT_NETWORK_NAME: "my-net"})

        async def _clean(network_def):
            return [], []

        async def _fake_persist(network_def, agent_network_name, sample_queries):
            return deploy_error

        monkeypatch.setattr(mw, "_validate_network", _clean)
        monkeypatch.setattr(mw, "_assemble_and_persist", _fake_persist)
        monkeypatch.setattr(mw, "_determine_exported_network_definition", lambda *a, **k: None)
        monkeypatch.delenv("AGENT_NETWORK_DESIGNER_PROGRESS_STYLE", raising=False)
        return mw

    def test_successful_persist_returns_none(self, monkeypatch):
        mw = self._mw_clean(monkeypatch, deploy_error=None)
        result = asyncio.run(mw.aafter_agent(None, None))
        assert result is None

    def test_deploy_error_returns_deploy_error_response_with_no_jump(self, monkeypatch):
        mw = self._mw_clean(monkeypatch, deploy_error="server rejected the temporary network")
        result = asyncio.run(mw.aafter_agent(None, None))
        assert "jump_to" not in result
        assert "server rejected the temporary network" in result["messages"][0].content


class TestAssembleAndPersistFrontManLookup:
    """Regression test for the .pop()-on-an-empty-set crash this class was
    fixed for: a network where every agent is a down-chain of another
    (e.g. a two-node cycle) has NO front man at all, and must raise a
    clear, catchable ValueError instead of an unhandled KeyError."""

    def test_cyclic_network_raises_a_clear_value_error(self, monkeypatch):
        mw = _middleware()

        async def _fake_create_persistor():
            return object(), {}

        monkeypatch.setattr(mw, "_create_persistor", _fake_create_persistor)

        cyclic_network_def = {
            "a": {"instructions": "x", "tools": ["b"]},
            "b": {"instructions": "y", "tools": ["a"]},
        }
        with pytest.raises(ValueError, match="Could not identify a front-man agent"):
            asyncio.run(mw._assemble_and_persist(cyclic_network_def, "my-net", []))
