import os
import zipfile

import pytest

from process_toolkit import paths
from process_toolkit.iac import generation


def test_save_and_load_round_trips_file_content():
    with paths.use_session("s1"):
        generation.save_iac_files({"main.tf": "resource \"x\" \"y\" {}\n"})
        loaded = generation.load_iac_files()
    assert loaded == {"main.tf": "resource \"x\" \"y\" {}\n"}


def test_save_preserves_one_level_of_subdirectory():
    with paths.use_session("s1"):
        generation.save_iac_files({"modules/vpc/main.tf": "content"})
        loaded = generation.load_iac_files()
    assert loaded == {"modules/vpc/main.tf": "content"}


def test_save_sanitizes_path_traversal_attempts():
    with paths.use_session("s1"):
        written = generation.save_iac_files({"../../etc/passwd": "evil", "ok.tf": "fine"})
        iac_dir = paths.output_dir(generation.IAC_SUBDIR)
    # ".." components are stripped per-part, never allowed to escape iac_dir.
    for path in written.values():
        assert os.path.commonpath([os.path.abspath(path), os.path.abspath(iac_dir)]) == os.path.abspath(iac_dir)
    assert "ok.tf" in written


def test_save_clears_stale_files_from_an_earlier_generation():
    with paths.use_session("s1"):
        generation.save_iac_files({"old.tf": "stale"})
        generation.save_iac_files({"new.tf": "fresh"})
        loaded = generation.load_iac_files()
    assert loaded == {"new.tf": "fresh"}


def test_zip_iac_files_requires_something_to_zip():
    with paths.use_session("s1"):
        with pytest.raises(FileNotFoundError):
            generation.zip_iac_files()


def test_zip_iac_files_bundles_everything_saved():
    with paths.use_session("s1"):
        generation.save_iac_files({"main.tf": "a", "variables.tf": "b"})
        zip_path = generation.zip_iac_files()
        assert generation.iac_zip_exists()
    with zipfile.ZipFile(zip_path) as zf:
        assert sorted(zf.namelist()) == ["main.tf", "variables.tf"]


def test_sessions_do_not_leak_iac_files_into_each_other():
    with paths.use_session("session-a"):
        generation.save_iac_files({"a.tf": "a-content"})
    with paths.use_session("session-b"):
        generation.save_iac_files({"b.tf": "b-content"})
        loaded_b = generation.load_iac_files()
    with paths.use_session("session-a"):
        loaded_a = generation.load_iac_files()
    assert loaded_a == {"a.tf": "a-content"}
    assert loaded_b == {"b.tf": "b-content"}
