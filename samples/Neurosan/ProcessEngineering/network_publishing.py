# network_publishing.py
#
# Publishes this project's Neuro-San agent networks as portable, resolved JSON per the
# real "Open Agentic Web" MVP Profile 0.2 spec (https://github.com/cognizant-ai-labs/
# agentic-web/blob/main/docs/worldwide_agentic_web_mvp_spec.md), section 3.3's own
# "Minimum Public Files" table: an agent-manifest.json mapping published network names to
# {front_man, hocon}, where "hocon" points to a resolved, data-only JSON document (includes
# and substitutions already expanded, no local-file dependencies).
#
# Scope, deliberately: this publishes DATA only (Tenet One of that spec -- a portable
# network representation). It does NOT attempt Tenet Two (browser execution) or Tenet
# Three (BYOK/pluggable inference) -- this platform remains a server-executed, server-
# funded system. That matches the spec's own named "Private stewards" extension (section
# 7): an operator-hosted Neuro San network that keeps credentials and policy on its own
# server while still publishing public agent-network data for other sites to load. See
# docs/AGENTIC_WEB_STANDARDS.md for the full scope/limitations writeup.
#
# This is Neuro-San-specific (depends on neuro_san's own AgentNetworkRestorer) and has no
# GCP/ADK equivalent -- ADK has no HOCON registries to publish; see that doc for why.

import glob
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from pyhocon import ConfigFactory
from pyhocon.exceptions import ConfigMissingException

from neuro_san.internals.graph.persistence.agent_network_restorer import AgentNetworkRestorer

_logger = logging.getLogger("ProcessArchitect.NetworkPublishing")

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_REGISTRIES_DIR = os.path.join(_PROJECT_ROOT, "registries")
_MANIFEST_PATH = os.path.join(_REGISTRIES_DIR, "manifest.hocon")

_NETWORKS_ROUTE_PREFIX = "/networks/"
_NETWORK_FILENAME_SUFFIX = ".network.json"

_public_names_lock = threading.Lock()
_public_names_cache: Optional[List[str]] = None

_resolved_lock = threading.Lock()
_resolved_cache: Dict[str, Optional[Dict[str, Any]]] = {}


def _is_public(value: Any) -> bool:
    """registries/manifest.hocon's own convention: a bare `true` is public; a
    `{"serve": true, "public": false}`-shaped dict is served but not publicly listed.
    Anything else (missing/unrecognized shape) defaults to public -- the manifest's own
    existing entries only ever use these two shapes."""
    if isinstance(value, bool):
        return value
    try:
        return bool(value.get("public", True))
    except AttributeError:
        return True


def _load_public_network_names() -> List[str]:
    """Parses registries/manifest.hocon (plain pyhocon -- this is a flat key/value
    manifest, not an agent-network HOCON file, so AgentNetworkRestorer is the wrong tool
    here) and returns the network name (the .hocon filename's own stem) for every entry
    that is public.

    KNOWN LIMITATION, documented rather than silently wrong: manifest.hocon's own
    `include "registries/generated/manifest.hocon"` is resolved by plain pyhocon relative
    to manifest.hocon's own directory, not the project root that file's own include
    statement assumes -- this logs a warning and treats that include as empty rather than
    failing. Today that generated manifest IS empty (nothing is designer-generated in this
    project yet), so this has no actual effect; if that changes, this function will not
    see those additional networks until it's updated to resolve that include correctly."""
    try:
        config = ConfigFactory.parse_file(_MANIFEST_PATH)
    except ConfigMissingException:
        _logger.warning("Could not parse %s -- no networks will be published.", _MANIFEST_PATH)
        return []

    names: List[str] = []
    for raw_key in config.keys():
        # pyhocon's own ConfigTree.keys() returns each quoted HOCON key's RAW text,
        # literal surrounding double-quote characters included (confirmed directly:
        # `"basic/music_nerd.hocon": true` yields the key '"basic/music_nerd.hocon"', not
        # 'basic/music_nerd.hocon') -- every key in this manifest is quoted (required,
        # since several contain "/"), so this strip is universal here, not conditional.
        key = raw_key.strip('"')
        if not key.endswith(".hocon"):
            continue
        if not _is_public(config[raw_key]):
            continue
        names.append(os.path.splitext(os.path.basename(key))[0])
    return names


def _get_public_network_names() -> List[str]:
    """Lazily builds _load_public_network_names's result ONCE per server process and
    reuses it -- same reasoning, and same pattern, as cli.py's own
    _get_agent_instructions_index: the registries on disk don't change during a single
    server run."""
    global _public_names_cache
    with _public_names_lock:
        if _public_names_cache is None:
            _public_names_cache = _load_public_network_names()
        return _public_names_cache


def _find_registry_file(name: str) -> Optional[str]:
    """Maps a network name back to its registries/**/<name>.hocon file, wherever it lives
    (top-level or a subdirectory, e.g. basic/music_nerd.hocon)."""
    pattern = os.path.join(_REGISTRIES_DIR, "**", f"{name}.hocon")
    matches = glob.glob(pattern, recursive=True)
    return matches[0] if matches else None


def front_man_name(tools: List[Any]) -> Optional[str]:
    """This project's own established convention (see basic/music_nerd.hocon's own header
    comment, and cli.py's own _build_agent_instructions_index, which computes this the same
    way): the front man is the first top-level tools entry that is a real agent definition
    (has both a name and instructions, as opposed to a bare same-server "/network" string
    reference or a CodedTool entry)."""
    for entry in tools or []:
        if isinstance(entry, dict) and entry.get("name") and entry.get("instructions"):
            return entry["name"]
    return None


def resolve_network(name: str) -> Optional[Dict[str, Any]]:
    """Returns the fully resolved (includes + substitutions expanded) Neuro-San network
    config for `name` -- the real agent-network data model the spec requires, already in
    the right shape straight from AgentNetworkRestorer.get_config() -- if `name` is a
    public network with a registry file. Returns None otherwise (unknown name, not public,
    or the registry failed to parse -- logged, not raised, same as
    _build_agent_instructions_index's own "one bad file must not take down the others"
    reasoning)."""
    with _resolved_lock:
        if name in _resolved_cache:
            return _resolved_cache[name]

        result: Optional[Dict[str, Any]] = None
        if name in _get_public_network_names():
            abs_path = _find_registry_file(name)
            if abs_path is not None:
                try:
                    restorer = AgentNetworkRestorer(registry_dir=None)
                    agent_network = restorer.restore(file_reference=abs_path)
                    config = agent_network.get_config()
                    if isinstance(config, dict) and isinstance(config.get("tools"), list):
                        result = config
                except Exception:  # pylint: disable=broad-except
                    _logger.warning("Could not resolve registry for network %r -- not published.", name)

        _resolved_cache[name] = result
        return result


def build_agent_network_manifest(base_url: str = "") -> Dict[str, Any]:
    """Builds the real agent-manifest.json content per the Open Agentic Web MVP spec's
    section 3.3 table: one entry per published network, each with the minimum required
    `name`/`front_man`/`hocon` fields (`hocon` here points to this project's own
    /networks/<name>.network.json route, not a literal HOCON file -- the spec explicitly
    allows a fully resolved JSON document; "<network>.network.json" is its own stated
    convention, not a requirement).

    links.json (the spec's peer-network link map) is intentionally not published: none of
    this project's own registries reference a genuinely external (different-origin) peer
    network today -- every cross-network reference (e.g. process_architect.hocon's own
    "/design_update") is a same-server internal reference, not a symbolic external one."""
    networks: Dict[str, Any] = {}
    for name in sorted(_get_public_network_names()):
        config = resolve_network(name)
        if config is None:
            continue
        tools = config.get("tools") or []
        metadata = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
        networks[name] = {
            "name": name,
            "description": metadata.get("description", ""),
            "front_man": front_man_name(tools),
            "hocon": f"{base_url}{_NETWORKS_ROUTE_PREFIX}{name}{_NETWORK_FILENAME_SUFFIX}",
        }
    return {"networks": networks}
