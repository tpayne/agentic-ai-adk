"""Regression tests for AgentNetworkDefinitionMiddleware -- previously
uncovered entirely (see the code review that added this file). Focuses on
the pure/sync helpers and the few branches cheap to exercise without a real
HOCON file or S3/boto3 round trip: UUID-suffix stripping, HOCON path
resolution (including the path-escape guard), per-agent parsing edge cases
(including the now-consolidated "store instructions as-is" behavior --
_extract_custom_instructions used to run here too, see
_strip_common_instructions's own docstring for why that was redundant), the
process-wide aaosa.hocon cache, and the model-call-gating branches of
abefore_model.
"""

import asyncio
import os

import pytest

from coded_tools.agent_network_editor.constants import AGENT_NETWORK_DEFINITION
from coded_tools.agent_network_editor.constants import AGENT_NETWORK_METADATA
from coded_tools.agent_network_editor.constants import AGENT_NETWORK_NAME
from middleware.agent_network_designer.agent_network_definition_middleware import (
    AGENT_NETWORK_HOCON_FILE,
)
from middleware.agent_network_designer.agent_network_definition_middleware import (
    AgentNetworkDefinitionMiddleware,
)
from middleware.agent_network_designer.agent_network_definition_middleware import SKIP_DESIGNER


def _middleware(sly_data=None):
    return AgentNetworkDefinitionMiddleware(sly_data if sly_data is not None else {})


@pytest.fixture(autouse=True)
def _reset_aaosa_cache(monkeypatch):
    # _aaosa_instructions is a CLASS-level, "first call wins" cache (see
    # _cache_aaosa_instructions) -- shared across every instance and every
    # test in this process. Without resetting it per test, whichever test
    # runs first silently decides the cached value for every test after it.
    monkeypatch.setattr(AgentNetworkDefinitionMiddleware, "_aaosa_instructions", None)


class TestExtractNameFromReservationId:
    """_extract_name_from_reservation_id -- strips the trailing "-<uuid4>"
    neuro-san's AgentReservation mints reservation ids with."""

    def test_strips_trailing_uuid_suffix(self):
        mw = _middleware()
        name = mw._extract_name_from_reservation_id("my-network-550e8400-e29b-41d4-a716-446655440000")
        assert name == "my-network"

    def test_uppercase_hex_also_matches(self):
        mw = _middleware()
        name = mw._extract_name_from_reservation_id("MyNet-550E8400-E29B-41D4-A716-446655440000")
        assert name == "MyNet"

    def test_bare_uuid_with_no_prefix_returns_unchanged(self):
        mw = _middleware()
        reservation_id = "550e8400-e29b-41d4-a716-446655440000"
        assert mw._extract_name_from_reservation_id(reservation_id) == reservation_id

    def test_id_with_no_uuid_suffix_at_all_returns_unchanged(self):
        mw = _middleware()
        assert mw._extract_name_from_reservation_id("just-a-plain-name") == "just-a-plain-name"


class TestResolveHoconPath:
    """_resolve_hocon_path -- validates and resolves a user-supplied HOCON
    reference; the path-escape guard here is security-relevant (a client
    sends this value directly in sly_data)."""

    def test_non_string_input_sets_error_and_returns_none(self):
        mw = _middleware()
        assert mw._resolve_hocon_path(123) is None
        assert "Invalid network_hocon_file value" in mw.error_message

    def test_blank_string_sets_error_and_returns_none(self):
        mw = _middleware()
        assert mw._resolve_hocon_path("   ") is None
        assert mw.error_message

    def test_absolute_posix_path_used_as_is(self):
        mw = _middleware()
        assert mw._resolve_hocon_path("/etc/some/network.hocon") == "/etc/some/network.hocon"

    def test_existing_repo_relative_path_used_as_is(self):
        # registries/aaosa.hocon is a real file checked into this project.
        mw = _middleware()
        assert mw._resolve_hocon_path("registries/aaosa.hocon") == "registries/aaosa.hocon"

    def test_backslashes_normalized_to_forward_slashes(self):
        mw = _middleware()
        assert mw._resolve_hocon_path("registries\\aaosa.hocon") == "registries/aaosa.hocon"

    def test_unknown_relative_path_falls_back_to_base_dir_not_an_escape(self):
        # A name that does not exist anywhere relative to cwd must resolve
        # under the registries base dir, not escape it via "../". base_dir
        # itself depends on AGENT_MANIFEST_FILE, which other test modules in
        # this same process may have already set (e.g. test_pipeline_middleware's
        # os.environ.setdefault at import time) -- mirror _resolve_hocon_path's
        # own base_dir computation here instead of hardcoding "registries",
        # so this test is correct regardless of module import order.
        from middleware.agent_network_designer.persistence.file_system_agent_network_persistor import (
            DEFAULT_REGISTRIES_DIR,
            FileSystemAgentNetworkPersistor,
        )

        first_manifest = FileSystemAgentNetworkPersistor.get_first_manifest_path()
        expected_base_dir = os.path.dirname(first_manifest) if first_manifest else DEFAULT_REGISTRIES_DIR

        mw = _middleware()
        resolved = mw._resolve_hocon_path("../../etc/passwd")
        # The leading "/".lstrip("/") step only strips slashes, not "..", so
        # this documents the guard's actual behavior: a non-existent,
        # non-absolute path is joined onto the registries base dir, which
        # still leaves a literal ".." component for pathlib to carry
        # through. Pin the exact, current resolution so a regression that
        # silently changes it (e.g. normalizing ".." away, or failing to
        # join against base_dir at all) is caught either way.
        assert resolved == os.path.join(expected_base_dir, "../../etc/passwd").replace(os.sep, "/")


class TestParseAgent:
    """_parse_agent -- per-entry validation of the HOCON/S3 'tools' list."""

    def test_non_dict_entry_is_skipped(self):
        mw = _middleware()
        name, agent_def = asyncio.run(mw._parse_agent("not-a-dict", "source.hocon"))
        assert name is None
        assert agent_def == {}

    def test_missing_name_is_skipped(self):
        mw = _middleware()
        name, _ = asyncio.run(mw._parse_agent({"instructions": "hi"}, "source.hocon"))
        assert name is None

    def test_non_string_name_is_skipped(self):
        mw = _middleware()
        name, _ = asyncio.run(mw._parse_agent({"name": 42}, "source.hocon"))
        assert name is None

    def test_non_string_instructions_is_skipped_entirely(self):
        mw = _middleware()
        name, agent_def = asyncio.run(mw._parse_agent({"name": "a", "instructions": 42}, "source.hocon"))
        assert name is None
        assert agent_def == {}

    def test_instructions_are_stored_as_is_not_extracted(self):
        # Regression test for the duplicate-stripping consolidation: this
        # middleware used to run its own ad hoc _extract_custom_instructions
        # here at parse time; that call was removed because
        # abefore_model's _strip_common_instructions already strips common
        # instruction copies from the WHOLE resolved network_def afterward,
        # regardless of source. _parse_agent must now pass instructions
        # through untouched.
        mw = _middleware()
        raw = "You are part of a demo system, so when queried, make up a realistic response. Custom bit."
        name, agent_def = asyncio.run(mw._parse_agent({"name": "a", "instructions": raw}, "source.hocon"))
        assert name == "a"
        assert agent_def["instructions"] == raw

    def test_non_string_description_is_skipped_entirely(self):
        mw = _middleware()
        name, agent_def = asyncio.run(
            mw._parse_agent({"name": "a", "function": {"description": 7}}, "source.hocon")
        )
        assert name is None
        assert agent_def == {}

    def test_tools_field_passed_through(self):
        mw = _middleware()
        name, agent_def = asyncio.run(mw._parse_agent({"name": "a", "tools": ["b", "c"]}, "source.hocon"))
        assert name == "a"
        assert agent_def["tools"] == ["b", "c"]


class TestConfigToNetworkDef:
    """_config_to_network_def -- converts a parsed HOCON/S3 config dict into
    an agent network definition, or reports why it could not (issue #1426:
    this must set error_message and return None, not an empty dict, on any
    failure -- callers test `if network_def:` to decide whether a load
    happened at all)."""

    def test_missing_tools_field_is_a_load_error(self):
        mw = _middleware()
        result = asyncio.run(mw._config_to_network_def({}, "source.hocon"))
        assert result is None
        assert "No field 'tools' found" in mw.error_message

    def test_tools_field_not_a_list_is_a_load_error(self):
        mw = _middleware()
        result = asyncio.run(mw._config_to_network_def({"tools": "not-a-list"}, "source.hocon"))
        assert result is None
        assert "not a list" in mw.error_message

    def test_every_entry_skipped_is_a_load_error_not_an_empty_network(self):
        mw = _middleware()
        result = asyncio.run(mw._config_to_network_def({"tools": ["not-a-dict"]}, "source.hocon"))
        assert result is None
        assert "No usable agent found" in mw.error_message

    def test_happy_path_builds_network_def_and_metadata(self):
        sly_data = {}
        mw = _middleware(sly_data)
        config = {"tools": [{"name": "front_man", "instructions": "Be helpful."}]}
        result = asyncio.run(mw._config_to_network_def(config, "source.hocon"))
        assert result == {"front_man": {"instructions": "Be helpful.", "description": ""}}
        assert AGENT_NETWORK_METADATA in sly_data


class TestAaosaInstructionsCache:
    """_read_aaosa_instructions / _cache_aaosa_instructions -- the
    process-wide, race-safe cache that replaced the old per-sly_data cache
    in _get_aaosa_instructions (removed; see the code review that
    consolidated the two)."""

    def test_cache_aaosa_instructions_first_writer_wins(self):
        assert AgentNetworkDefinitionMiddleware._cache_aaosa_instructions("first") is True
        assert AgentNetworkDefinitionMiddleware._aaosa_instructions == "first"
        # A second call must NOT overwrite an already-cached value.
        assert AgentNetworkDefinitionMiddleware._cache_aaosa_instructions("second") is False
        assert AgentNetworkDefinitionMiddleware._aaosa_instructions == "first"

    def test_read_returns_cached_value_without_touching_the_filesystem(self, monkeypatch):
        AgentNetworkDefinitionMiddleware._aaosa_instructions = "cached value"

        def _boom(*_args, **_kwargs):
            raise AssertionError("must not read the file when already cached")

        monkeypatch.setattr(os.path, "exists", _boom)
        mw = _middleware()
        result = asyncio.run(mw._read_aaosa_instructions())
        assert result == "cached value"

    def test_read_loads_and_caches_the_real_registry_file(self):
        mw = _middleware()
        result = asyncio.run(mw._read_aaosa_instructions())
        assert result  # registries/aaosa.hocon defines a non-empty aaosa_instructions
        assert AgentNetworkDefinitionMiddleware._aaosa_instructions == result


class TestBeforeModel:
    """abefore_model -- the main entry point: resolves/normalizes the
    network definition and gates whether the model call proceeds at all."""

    def test_missing_name_for_an_inline_definition_is_an_error(self):
        sly_data = {AGENT_NETWORK_DEFINITION: {"a": {"instructions": "hi"}}}
        mw = _middleware(sly_data)
        result = asyncio.run(mw.abefore_model(None, None))
        assert result["jump_to"] == "end"
        assert f'"{AGENT_NETWORK_NAME}" is missing' in result["messages"][0].content

    def test_non_string_name_is_an_error(self):
        sly_data = {AGENT_NETWORK_DEFINITION: {"a": {"instructions": "hi"}}, AGENT_NETWORK_NAME: 42}
        mw = _middleware(sly_data)
        result = asyncio.run(mw.abefore_model(None, None))
        assert result["jump_to"] == "end"
        assert "has to be str" in result["messages"][0].content

    def test_valid_inline_definition_proceeds_and_normalizes(self):
        sly_data = {
            AGENT_NETWORK_DEFINITION: {"a": {"instructions": "hi"}},
            AGENT_NETWORK_NAME: "my-net",
        }
        mw = _middleware(sly_data)
        result = asyncio.run(mw.abefore_model(None, None))
        assert result is None
        assert mw.network_def == {"a": {"instructions": "hi"}}

    def test_skip_designer_true_jumps_to_end_with_notification(self):
        sly_data = {
            AGENT_NETWORK_DEFINITION: {"a": {"instructions": "hi"}},
            AGENT_NETWORK_NAME: "my-net",
            SKIP_DESIGNER: True,
        }
        mw = _middleware(sly_data)
        result = asyncio.run(mw.abefore_model(None, None))
        assert result["jump_to"] == "end"
        assert "my-net" in result["messages"][0].content

    def test_skip_designer_false_proceeds_normally(self):
        sly_data = {
            AGENT_NETWORK_DEFINITION: {"a": {"instructions": "hi"}},
            AGENT_NETWORK_NAME: "my-net",
            SKIP_DESIGNER: False,
        }
        mw = _middleware(sly_data)
        result = asyncio.run(mw.abefore_model(None, None))
        assert result is None

    def test_missing_hocon_file_path_is_reported_as_load_error(self):
        sly_data = {AGENT_NETWORK_HOCON_FILE: "registries/does-not-exist-at-all.hocon"}
        mw = _middleware(sly_data)
        result = asyncio.run(mw.abefore_model(None, None))
        assert result["jump_to"] == "end"
        assert "not found" in result["messages"][0].content

    def test_no_definition_at_all_proceeds_with_none(self):
        # No AGENT_NETWORK_DEFINITION, no AGENT_NETWORK_HOCON_FILE, no
        # AGENT_RESERVATIONS -- nothing to resolve, nothing to report.
        mw = _middleware({})
        result = asyncio.run(mw.abefore_model(None, None))
        assert result is None
        assert mw.network_def is None
