from process_toolkit.feedback.iteration_feedback import (
    format_review_status_summary,
    load_iteration_feedback,
    save_iteration_feedback,
)


def test_save_then_load_round_trips_and_drains():
    save_iteration_feedback({"status": "REVISION REQUIRED", "issues": [{"instruction": "fix X"}]})

    first_read = load_iteration_feedback()
    assert first_read["status"] == "REVISION REQUIRED"
    assert first_read["data"] == [{"instruction": "fix X"}]

    second_read = load_iteration_feedback()
    assert second_read["status"] == "NONE"
    assert second_read["data"] == []


def test_approval_marker_updates_cumulative_approval_state():
    save_iteration_feedback({"status": "CLOUDARCH APPROVED", "data": []})

    import json
    from process_toolkit.feedback.iteration_feedback import APPROVAL_FILENAME
    from process_toolkit.paths import output_path

    with open(output_path(APPROVAL_FILENAME), "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["cloudarch_status"] == "APPROVED"


def test_iac_approved_marker_updates_cumulative_approval_state():
    # Regression for the CloudArch_IaC_Pipeline feature -- IAC APPROVED
    # must be a registered marker, same as every other reviewer's own
    # "<DOMAIN> APPROVED" string, or loop_control's own
    # required={"iac_status": "APPROVED"} check would never be satisfied.
    save_iteration_feedback({"status": "IAC APPROVED", "data": []}, channel="iac")

    import json
    from process_toolkit.feedback.iteration_feedback import APPROVAL_FILENAME
    from process_toolkit.paths import output_path

    with open(output_path(APPROVAL_FILENAME), "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["iac_status"] == "APPROVED"


def test_togaf_compliance_approved_marker_updates_cumulative_approval_state():
    # Regression for the TOGAF pipeline feature -- TOGAF_COMPLIANCE_APPROVED
    # must be a registered marker, matching the literal "status" value
    # TOGAF_Compliance_Agent saves, or loop_control's own
    # required={"togaf_compliance_status": "APPROVED"} check would never
    # be satisfied.
    save_iteration_feedback({"status": "TOGAF_COMPLIANCE_APPROVED", "data": []}, channel="togaf_compliance")

    import json
    from process_toolkit.feedback.iteration_feedback import APPROVAL_FILENAME
    from process_toolkit.paths import output_path

    with open(output_path(APPROVAL_FILENAME), "r", encoding="utf-8") as f:
        state = json.load(f)
    assert state["togaf_compliance_status"] == "APPROVED"


def test_separate_channels_do_not_overwrite_each_other():
    """The exact bug the ADK original's per-reviewer refinement clones
    existed to avoid: two reviewers writing feedback in the same pass must
    not clobber each other if they're on different channels."""
    save_iteration_feedback({"status": "REVISION REQUIRED", "issues": ["compliance issue"]}, channel="compliance")
    save_iteration_feedback({"status": "SIMULATION_ALL_APPROVED", "data": []}, channel="simulation")

    compliance_fb = load_iteration_feedback(channel="compliance")
    simulation_fb = load_iteration_feedback(channel="simulation")

    assert compliance_fb["data"] == ["compliance issue"]
    assert simulation_fb["status"] == "SIMULATION_ALL_APPROVED"


def test_default_channel_is_independent_of_named_channels():
    save_iteration_feedback({"status": "REVISION REQUIRED", "issues": ["default channel issue"]})
    save_iteration_feedback({"status": "REVISION REQUIRED", "issues": ["named channel issue"]}, channel="analysis")

    default_fb = load_iteration_feedback()
    analysis_fb = load_iteration_feedback(channel="analysis")

    assert default_fb["data"] == ["default channel issue"]
    assert analysis_fb["data"] == ["named channel issue"]


def test_format_review_status_summary_reports_approved_channels():
    save_iteration_feedback({"status": "COMPLIANCE APPROVED", "notes": "all good"}, channel="compliance")
    save_iteration_feedback({"status": "SIMULATION_ALL_APPROVED", "notes": "all good"}, channel="simulation")

    summary = format_review_status_summary(channels=("compliance", "simulation"))

    assert "Compliance: APPROVED." in summary
    assert "Simulation: APPROVED." in summary


def test_format_review_status_summary_names_the_real_open_issues_verbatim():
    # Regression test for a real production bug: a pipeline's own final
    # report named SPOFs that were never in the real simulation data and
    # omitted real, open security/latency risks that were. This function
    # must surface the ACTUAL persisted instruction text, not a
    # paraphrase.
    save_iteration_feedback(
        {
            "status": "REVISION REQUIRED",
            "issues": [
                {
                    "issue_type": "simulation",
                    "location": "high_level_design.availability_and_resilience",
                    "instruction": "Redis, Message Broker, and Checkout Orchestrator are SPOFs.",
                },
                {
                    "issue_type": "simulation",
                    "location": "high_level_design.scalability_and_performance",
                    "instruction": "latency_budget_risk is true for the Edge Rate Limiter chain.",
                },
            ],
        },
        channel="simulation",
    )

    summary = format_review_status_summary(channels=("simulation",))

    assert "Redis, Message Broker, and Checkout Orchestrator are SPOFs." in summary
    assert "latency_budget_risk is true for the Edge Rate Limiter chain." in summary
    assert "Payment Gateway" not in summary


def test_format_review_status_summary_does_not_drain_the_mailbox():
    save_iteration_feedback({"status": "REVISION REQUIRED", "issues": [{"instruction": "fix X"}]}, channel="compliance")

    format_review_status_summary(channels=("compliance",))

    still_there = load_iteration_feedback(reset_data=False, channel="compliance")
    assert still_there["data"] == [{"instruction": "fix X"}]


def test_format_review_status_summary_handles_no_review_yet():
    summary = format_review_status_summary(channels=("compliance", "simulation"))
    assert "no review has run yet this turn" in summary
