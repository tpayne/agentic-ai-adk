from coded_tools.requirements_summary.load_directory_context_tool import LoadDirectoryContextCodedTool
from coded_tools.requirements_summary.save_requirements_summary_tool import SaveRequirementsSummaryCodedTool
from coded_tools.requirements_consultant.load_requirements_summary_tool import LoadRequirementsSummaryCodedTool


def test_save_then_load_round_trips_the_summary():
    save_tool = SaveRequirementsSummaryCodedTool()
    load_tool = LoadRequirementsSummaryCodedTool()
    sly_data = {}

    summary = {"source_directory": "./vendor-docs", "summary": "Vendor onboarding needs KYC checks."}
    result = save_tool.invoke({"summary": summary}, sly_data)
    assert result.startswith("SUCCESS:")

    loaded = load_tool.invoke({}, sly_data)
    assert loaded["status"] == "OK"
    assert loaded["summary"] == "Vendor onboarding needs KYC checks."


def test_load_without_a_prior_save_returns_not_found():
    load_tool = LoadRequirementsSummaryCodedTool()
    result = load_tool.invoke({}, {})
    assert result == {"status": "NOT_FOUND"}


def test_concurrent_sessions_do_not_see_each_others_summary():
    """Each session has its own sly_data -- session A's save must not leak
    into session B's own-session load, even though both share the same
    on-disk file as a cross-process fallback."""
    save_tool = SaveRequirementsSummaryCodedTool()
    load_tool = LoadRequirementsSummaryCodedTool()

    session_a, session_b = {}, {}
    save_tool.invoke({"summary": {"summary": "session A"}}, session_a)
    save_tool.invoke({"summary": {"summary": "session B"}}, session_b)

    assert load_tool.invoke({}, session_a)["summary"] == "session A"
    assert load_tool.invoke({}, session_b)["summary"] == "session B"

    # A brand new session that never saved falls back to the shared file
    # (whichever save happened last).
    fresh_session = {}
    assert load_tool.invoke({}, fresh_session)["summary"] == "session B"


def test_save_rejects_non_dict_input():
    save_tool = SaveRequirementsSummaryCodedTool()
    result = save_tool.invoke({"summary": ["not", "a", "dict"]}, {})
    assert result.startswith("ERROR:")


def test_load_directory_context_tool_requires_directory_argument():
    tool = LoadDirectoryContextCodedTool()
    result = tool.invoke({}, {})
    assert result["status"] == "ERROR"
