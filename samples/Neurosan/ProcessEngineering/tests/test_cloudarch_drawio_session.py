"""Regression coverage for sandboxing output/cloudarch_drawio.xml to the
chat session using it: a diagram left behind by an earlier, unrelated
session must never be silently presented as "the current architecture"
by a fresh session's generate/refine pipeline or its read-only query
agents (consultant/simulation/attack-simulation/finops).
"""

from process_toolkit import paths
from process_toolkit.drawio.persistence import DRAWIO_FILENAME


def _write_stale_drawio(content: str = "stale-content") -> str:
    path = paths.output_path(DRAWIO_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_claim_returns_true_once_then_false_for_the_same_session():
    from coded_tools.common.cloudarch_drawio_session import claim_cloudarch_drawio_for_session

    sly_data = {}
    assert claim_cloudarch_drawio_for_session(sly_data) is True
    assert claim_cloudarch_drawio_for_session(sly_data) is False
    assert claim_cloudarch_drawio_for_session(sly_data) is False


def test_claim_is_independent_across_separate_sly_data_dicts():
    from coded_tools.common.cloudarch_drawio_session import claim_cloudarch_drawio_for_session

    assert claim_cloudarch_drawio_for_session({}) is True
    assert claim_cloudarch_drawio_for_session({}) is True


def test_cloudarch_reset_loop_state_clears_a_stale_drawio_file_on_first_touch():
    # The actual bug: a brand-new session's first generate-or-refine
    # request must not silently inherit a diagram some OTHER, unrelated
    # session left behind.
    from coded_tools.cloudarch.reset_loop_state_tool import ResetLoopStateCodedTool

    path = _write_stale_drawio()
    result = ResetLoopStateCodedTool().invoke({}, {})
    assert result["status"] == "OK"
    assert not __import__("os").path.exists(path)


def test_cloudarch_reset_loop_state_leaves_a_same_session_diagram_untouched_on_a_later_touch():
    # The legitimate counterpart: a second, later generate/refine request
    # in the SAME session must not have its own just-generated diagram
    # wiped out.
    import os

    from coded_tools.cloudarch.reset_loop_state_tool import ResetLoopStateCodedTool
    from process_toolkit.run_lock import release_pipeline_lock
    from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY

    tool = ResetLoopStateCodedTool()
    sly_data = {}
    first = tool.invoke({}, sly_data)
    assert first["status"] == "OK"
    # Release the lock the first call claimed, simulating that turn's
    # pipeline genuinely finishing, before the second turn's reset call.
    release_pipeline_lock(sly_data.get(PIPELINE_LOCK_TOKEN_KEY))

    path = _write_stale_drawio("this-sessions-own-diagram")
    second = tool.invoke({}, sly_data)
    assert second["status"] == "OK"
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        assert f.read() == "this-sessions-own-diagram"


def test_process_pipelines_own_reset_loop_state_never_touches_the_drawio_file():
    # Regression guard for the re-export trap: process/design/*_update's
    # own reset_loop_state_tool.py files must keep pointing at the
    # generic base (no drawio awareness at all), NOT at CloudArch's own
    # subclass -- otherwise an unrelated process/design pipeline run
    # would delete a cloud architecture diagram the user never asked
    # about.
    from coded_tools.process.reset_loop_state_tool import ResetLoopStateCodedTool as ProcessReset
    from coded_tools.design.reset_loop_state_tool import ResetLoopStateCodedTool as DesignReset
    from coded_tools.cloudarch.reset_loop_state_tool import ResetLoopStateCodedTool as CloudArchReset

    assert ProcessReset is DesignReset
    assert ProcessReset is not CloudArchReset

    path = _write_stale_drawio("should-survive-an-unrelated-process-run")
    result = ProcessReset().invoke({}, {})
    assert result["status"] == "OK"
    assert __import__("os").path.exists(path)


def test_load_drawio_claims_the_session_without_deleting_the_file():
    # A read-only question must never destroy a diagram just because
    # this session hasn't looked at it yet.
    from coded_tools.cloudarch.load_drawio_tool import LoadDrawioCodedTool
    from coded_tools.common.cloudarch_drawio_session import CLOUDARCH_DRAWIO_SESSION_OWNED_KEY

    path = _write_stale_drawio("someone-elses-diagram")
    sly_data = {}
    result = LoadDrawioCodedTool().invoke({}, sly_data)

    assert result["status"] == "OK"
    assert result["xml"] == "someone-elses-diagram"
    assert __import__("os").path.exists(path)
    assert sly_data[CLOUDARCH_DRAWIO_SESSION_OWNED_KEY] is True


def test_a_readonly_query_before_a_refine_request_in_the_same_session_preserves_the_diagram():
    # Regression test for the ordering trap: a read-only query that runs
    # FIRST in a session claims ownership non-destructively; a refine
    # request in that SAME session afterward must see the session as
    # already "owned" and must not retroactively delete the diagram the
    # query just presented.
    import os

    from coded_tools.cloudarch.load_drawio_tool import LoadDrawioCodedTool
    from coded_tools.cloudarch.reset_loop_state_tool import ResetLoopStateCodedTool

    sly_data = {}
    path = _write_stale_drawio("asked-about-this-one")

    query_result = LoadDrawioCodedTool().invoke({}, sly_data)
    assert query_result["status"] == "OK"
    assert os.path.exists(path)

    refine_result = ResetLoopStateCodedTool().invoke({}, sly_data)
    assert refine_result["status"] == "OK"
    assert os.path.exists(path)
