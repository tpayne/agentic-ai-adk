import network_publishing as np


def test_public_network_names_includes_the_real_pipelines_and_excludes_internal_support_networks():
    names = np._get_public_network_names()

    for expected in ("design", "process_architect", "cloudarch_finops", "togaf", "music_nerd"):
        assert expected in names

    # registries/manifest.hocon explicitly marks these "public": false -- served (so the
    # live server still runs them) but not meant to be publicly listed/discoverable.
    for internal in (
        "agent_network_editor",
        "agent_network_instructions_editor",
        "agent_network_query_generator",
        "cruse_theme_agent",
        "cruse_widget_agent",
    ):
        assert internal not in names


def test_resolve_network_returns_a_real_resolved_config_for_a_public_network():
    config = np.resolve_network("design")
    assert config is not None
    assert isinstance(config.get("tools"), list)
    assert config["tools"][0]["name"] == "Design_Doc_Pipeline"
    assert "metadata" in config


def test_resolve_network_returns_none_for_an_unknown_name():
    assert np.resolve_network("totally_made_up_network_name_xyz") is None


def test_resolve_network_returns_none_for_an_internal_non_public_network():
    # agent_network_editor.hocon is a real, parseable registry file, but it's explicitly
    # "public": false -- resolve_network must not publish it just because the file exists.
    assert np.resolve_network("agent_network_editor") is None


def test_front_man_name_is_the_first_tool_entry_with_both_name_and_instructions():
    tools = [
        "/some_external_reference",
        {"name": "CodedToolOnly", "class": "some.module.Tool"},
        {"name": "RealFrontMan", "instructions": "Do the thing."},
        {"name": "SecondAgent", "instructions": "Also do a thing."},
    ]
    assert np.front_man_name(tools) == "RealFrontMan"


def test_front_man_name_returns_none_for_an_empty_or_agentless_tools_list():
    assert np.front_man_name([]) is None
    assert np.front_man_name(["/only_an_external_reference"]) is None


def test_build_agent_network_manifest_shape():
    manifest = np.build_agent_network_manifest(base_url="http://example.test")
    networks = manifest["networks"]

    assert "design" in networks
    entry = networks["design"]
    assert entry["name"] == "design"
    assert entry["front_man"] == "Design_Doc_Pipeline"
    assert entry["hocon"] == "http://example.test/networks/design.network.json"
    assert entry["description"]

    # Every published entry has the spec's own minimum-required fields.
    for name, published in networks.items():
        assert published["name"] == name
        assert published["front_man"], f"{name} is missing a front_man"
        assert published["hocon"].startswith("http://example.test/networks/")

    # Internal/non-public networks never appear.
    assert "agent_network_editor" not in networks


def test_build_agent_network_manifest_respects_base_url():
    manifest = np.build_agent_network_manifest(base_url="https://other.example")
    assert manifest["networks"]["process_architect"]["hocon"] == (
        "https://other.example/networks/process_architect.network.json"
    )
