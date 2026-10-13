from process_toolkit.loop_control import evaluate_loop_stop


def test_continues_while_unapproved_and_under_max_iterations():
    decision = evaluate_loop_stop(
        loop_count=1, max_iterations=3, hard_stop=False,
        approval_state={}, required_approvals={"cloudarch_status": "APPROVED"},
    )
    assert decision.verdict == "CONTINUE"
    assert decision.iteration == 1
    assert decision.max_iterations == 3


def test_approval_on_the_final_allowed_iteration_reports_as_approved_not_exhausted():
    # Regression test: the approval-state check must run BEFORE the
    # max-iteration check -- a genuine approval on the last allowed
    # iteration must not be reported as "exhausted".
    decision = evaluate_loop_stop(
        loop_count=2, max_iterations=2, hard_stop=False,
        approval_state={"cloudarch_status": "APPROVED"},
        required_approvals={"cloudarch_status": "APPROVED"},
    )
    assert decision.verdict == "STOP"
    assert decision.reason == "APPROVED"


def test_hits_max_iterations_when_never_approved():
    decision = evaluate_loop_stop(
        loop_count=2, max_iterations=2, hard_stop=False,
        approval_state={}, required_approvals={"cloudarch_status": "APPROVED"},
    )
    assert decision.verdict == "STOP"
    assert decision.reason == "MAX_ITERATIONS"


def test_hard_stop_overrides_everything():
    decision = evaluate_loop_stop(
        loop_count=1, max_iterations=10, hard_stop=True,
        approval_state={}, required_approvals={"x": "APPROVED"},
    )
    assert decision.verdict == "STOP"
    assert decision.reason == "HARD_STOP"


def test_json_approved_status_stops_regardless_of_required_approvals():
    decision = evaluate_loop_stop(
        loop_count=1, max_iterations=10, hard_stop=False,
        approval_state={"status": "JSON APPROVED"},
        required_approvals={"compliance_status": "APPROVED"},
    )
    assert decision.verdict == "STOP"
    assert decision.reason == "APPROVED"
