import json
import os
import time

import pytest

from process_toolkit import paths
from process_toolkit.paths import (
    SESSION_META_FILENAME,
    output_dir,
    output_path,
    sanitize_session_id,
    use_session,
)


def test_no_session_active_resolves_flat_exactly_as_before():
    # The entire existing test suite (and every non-daemon CLI mode) never
    # calls use_session() -- this is the behavior that must stay
    # byte-for-byte unchanged.
    p = output_path("foo.json")
    assert p == os.path.join(paths.OUTPUT_DIR, "foo.json")
    d = output_dir("subprocesses")
    assert d == os.path.join(paths.OUTPUT_DIR, "subprocesses")


def test_use_session_scopes_output_path_under_a_subdirectory():
    with use_session("session-a"):
        p = output_path("foo.json")
    assert p == os.path.join(paths.OUTPUT_DIR, "session-a", "foo.json")


def test_two_sessions_resolve_to_different_files():
    with use_session("session-a"):
        pa = output_path("foo.json")
    with use_session("session-b"):
        pb = output_path("foo.json")
    assert pa != pb
    assert "session-a" in pa
    assert "session-b" in pb


def test_output_path_falls_back_to_flat_once_the_session_block_exits():
    with use_session("session-a"):
        output_path("foo.json")
    p = output_path("bar.json")
    assert p == os.path.join(paths.OUTPUT_DIR, "bar.json")


def test_use_session_with_none_is_a_no_op():
    with use_session(None):
        p = output_path("foo.json")
    assert p == os.path.join(paths.OUTPUT_DIR, "foo.json")


def test_use_session_restores_the_outer_session_on_nested_exit():
    # Not a real call pattern today, but the contextvar.reset() contract
    # should hold regardless: exiting an inner use_session() must restore
    # exactly what was active before it, not fall through to "no session".
    with use_session("outer"):
        with use_session("inner"):
            inner_path = output_path("x.json")
        outer_path = output_path("x.json")
    assert "inner" in inner_path
    assert "outer" in outer_path
    assert "inner" not in outer_path


def test_use_session_writes_a_session_metadata_file():
    with use_session("session-a"):
        pass
    meta_path = os.path.join(paths.OUTPUT_DIR, "session-a", SESSION_META_FILENAME)
    assert os.path.isfile(meta_path)
    with open(meta_path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data["last_active"], (int, float))
    assert data["last_active"] <= time.time()


def test_sanitize_session_id_accepts_a_realistic_uuid():
    assert sanitize_session_id("3f3a9c2e-7b4b-4b8e-9f1a-0b2c3d4e5f6a") == "3f3a9c2e-7b4b-4b8e-9f1a-0b2c3d4e5f6a"


@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "a/b", "", "..", ".", "a" * 200])
def test_sanitize_session_id_rejects_path_traversal_and_malformed_ids(bad_id):
    with pytest.raises(ValueError):
        sanitize_session_id(bad_id)


def test_use_session_with_a_malicious_id_raises_before_touching_disk():
    with pytest.raises(ValueError):
        with use_session("../../etc/passwd"):
            pass
