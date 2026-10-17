import asyncio

from coded_tools.cloudarch.load_attached_files_tool import (
    LoadAttachedFilesCodedTool,
    ATTACHED_FILES_SLY_DATA_KEY,
)


def test_returns_none_status_when_sly_data_has_no_attachments():
    assert LoadAttachedFilesCodedTool().invoke({}, {}) == {"status": "NONE"}


def test_returns_none_status_when_sly_data_is_not_a_dict():
    assert LoadAttachedFilesCodedTool().invoke({}, None) == {"status": "NONE"}


def test_returns_none_status_when_attached_files_key_is_an_empty_list():
    assert LoadAttachedFilesCodedTool().invoke({}, {ATTACHED_FILES_SLY_DATA_KEY: []}) == {"status": "NONE"}


def test_returns_the_attached_files_list_verbatim():
    files = [
        {"name": "spec.md", "mime_type": "text/markdown", "status": "OK", "text": "# Spec"},
        {"name": "diagram.png", "mime_type": "image/png", "status": "UNSUPPORTED", "reason": "not readable as text"},
    ]
    result = LoadAttachedFilesCodedTool().invoke({}, {ATTACHED_FILES_SLY_DATA_KEY: files})
    assert result == {"status": "OK", "files": files}


def test_async_invoke_matches_sync_invoke():
    files = [{"name": "a.txt", "mime_type": "text/plain", "status": "OK", "text": "hi"}]
    sly_data = {ATTACHED_FILES_SLY_DATA_KEY: files}
    sync_result = LoadAttachedFilesCodedTool().invoke({}, sly_data)
    async_result = asyncio.run(LoadAttachedFilesCodedTool().async_invoke({}, sly_data))
    assert sync_result == async_result
