"""Tests validating the iterative review loop mechanics for the requirements,
portfolio backlog, and project plan pipelines in Neurosan:
- reset_loop_state clears prior stop_counter.json and approval.json
- save_iteration_feedback updates approval.json with expected status markers
- loop_control writes/increments stop_counter.json during iterations
- loop_control returns CONTINUE on iteration 1 and STOP upon APPROVAL or MAX_ITERATIONS
"""

import json
import os
import pytest

from coded_tools.common.loop_control import LoopControlCodedTool
from coded_tools.common.reset_loop_state_base import ResetLoopStateCodedTool
from process_toolkit.feedback.iteration_feedback import (
    save_iteration_feedback,
    load_iteration_feedback,
    reset_approval_state,
    reset_feedback_channels,
)
from process_toolkit.paths import output_path


def test_requirements_review_loop_cycle():
    reset_tool = ResetLoopStateCodedTool()
    loop_tool = LoopControlCodedTool()

    # Step 1: reset loop state
    reset_tool.invoke({}, {})
    assert not os.path.exists(output_path("stop_counter.json"))
    assert not os.path.exists(output_path("approval.json"))

    # Step 2: iteration 1 without approval
    res1 = loop_tool.invoke({
        "required": {"requirements_review_status": "APPROVED"},
        "max_iterations": 2,
    }, {})
    assert res1["verdict"] == "CONTINUE"
    assert res1["iteration"] == 1
    # stop_counter.json must exist and equal 1
    assert os.path.exists(output_path("stop_counter.json"))
    with open(output_path("stop_counter.json"), "r") as f:
        assert json.load(f)["count"] == 1

    # Step 3: Reviewer posts approval
    save_iteration_feedback(
        feedback_data={"status": "REQUIREMENTS_REVIEW_APPROVED", "data": []},
        channel="requirements_reviewer",
    )
    assert os.path.exists(output_path("approval.json"))
    with open(output_path("approval.json"), "r") as f:
        approval = json.load(f)
        assert approval.get("requirements_review_status") == "APPROVED"

    # Step 4: iteration 2 evaluates approval and stops
    res2 = loop_tool.invoke({
        "required": {"requirements_review_status": "APPROVED"},
        "max_iterations": 2,
    }, {})
    assert res2["verdict"] == "STOP"
    assert res2["reason"] == "APPROVED"
    assert not os.path.exists(output_path("stop_counter.json"))


def test_portfolio_backlog_review_loop_cycle():
    reset_tool = ResetLoopStateCodedTool()
    loop_tool = LoopControlCodedTool()

    # Step 1: reset loop state
    reset_tool.invoke({}, {})
    assert not os.path.exists(output_path("stop_counter.json"))
    assert not os.path.exists(output_path("approval.json"))

    # Step 2: iteration 1 without approval
    res1 = loop_tool.invoke({
        "required": {"portfolio_backlog_review_status": "APPROVED"},
        "max_iterations": 2,
    }, {})
    assert res1["verdict"] == "CONTINUE"
    assert res1["iteration"] == 1
    assert os.path.exists(output_path("stop_counter.json"))

    # Step 3: Reviewer posts approval
    save_iteration_feedback(
        feedback_data={"status": "PORTFOLIO_BACKLOG_REVIEW_APPROVED", "data": []},
        channel="portfolio_backlog_reviewer",
    )
    with open(output_path("approval.json"), "r") as f:
        approval = json.load(f)
        assert approval.get("portfolio_backlog_review_status") == "APPROVED"

    # Step 4: iteration 2 evaluates approval and stops
    res2 = loop_tool.invoke({
        "required": {"portfolio_backlog_review_status": "APPROVED"},
        "max_iterations": 2,
    }, {})
    assert res2["verdict"] == "STOP"
    assert res2["reason"] == "APPROVED"


def test_project_plan_review_loop_cycle():
    reset_tool = ResetLoopStateCodedTool()
    loop_tool = LoopControlCodedTool()

    # Step 1: reset loop state
    reset_tool.invoke({}, {})
    assert not os.path.exists(output_path("stop_counter.json"))
    assert not os.path.exists(output_path("approval.json"))

    # Step 2: iteration 1 without approval
    res1 = loop_tool.invoke({
        "required": {"project_plan_review_status": "APPROVED"},
        "max_iterations": 2,
    }, {})
    assert res1["verdict"] == "CONTINUE"
    assert res1["iteration"] == 1
    assert os.path.exists(output_path("stop_counter.json"))

    # Step 3: Reviewer posts approval
    save_iteration_feedback(
        feedback_data={"status": "PROJECT_PLAN_REVIEW_APPROVED", "data": []},
        channel="project_plan_reviewer",
    )
    with open(output_path("approval.json"), "r") as f:
        approval = json.load(f)
        assert approval.get("project_plan_review_status") == "APPROVED"

    # Step 4: iteration 2 evaluates approval and stops
    res2 = loop_tool.invoke({
        "required": {"project_plan_review_status": "APPROVED"},
        "max_iterations": 2,
    }, {})
    assert res2["verdict"] == "STOP"
    assert res2["reason"] == "APPROVED"
