"""End-to-end simulations of what a front-man's orchestration does, calling
the real CodedTool classes in the same sequence the HOCON instructions
describe -- without needing a real LLM. Catches wiring bugs the individual
unit tests above wouldn't (e.g. a channel name typo between two tools)."""

from coded_tools.cloudarch.load_drawio_tool import LoadDrawioCodedTool
from coded_tools.cloudarch.loop_control_tool import LoopControlCodedTool as CloudArchLoopControl
from coded_tools.cloudarch.reset_loop_state_tool import ResetLoopStateCodedTool as CloudArchReset
from coded_tools.cloudarch.save_drawio_structured_tool import SaveDrawioStructuredCodedTool
from coded_tools.cloudarch.save_iteration_feedback_tool import (
    SaveIterationFeedbackCodedTool as CloudArchSaveFeedback,
)
from coded_tools.process.loop_control_tool import LoopControlCodedTool as ProcessLoopControl
from coded_tools.process.process_json_tool import (
    LoadMasterProcessJsonCodedTool,
    PersistFinalJsonCodedTool,
)
from coded_tools.process.reset_loop_state_tool import ResetLoopStateCodedTool as ProcessReset
from coded_tools.process.save_iteration_feedback_tool import (
    SaveIterationFeedbackCodedTool as ProcessSaveFeedback,
)


def test_cloudarch_pipeline_approves_on_first_pass():
    CloudArchReset().invoke({}, {})

    save_drawio = SaveDrawioStructuredCodedTool()
    result = save_drawio.invoke({
        "title": "Checkout Service", "zones": [{"id": "edge", "label": "Edge"}],
        "components": [{"id": "waf", "zone_id": "edge", "label": "WAF"}], "edges": [],
    }, {})
    assert result["status"] == "OK"

    CloudArchSaveFeedback().invoke({"feedback": {"status": "CLOUDARCH APPROVED", "data": []}}, {})

    verdict = CloudArchLoopControl().invoke(
        {"required": {"cloudarch_status": "APPROVED"}, "max_iterations": 2}, {}
    )
    assert verdict == {"verdict": "STOP", "reason": "APPROVED"}
    assert LoadDrawioCodedTool().invoke({}, {})["status"] == "OK"


def test_cloudarch_pipeline_continues_then_stops_at_max_iterations_if_never_approved():
    CloudArchReset().invoke({}, {})
    loop_control = CloudArchLoopControl()
    required = {"cloudarch_status": "APPROVED"}

    first = loop_control.invoke({"required": required, "max_iterations": 2}, {})
    assert first["verdict"] == "CONTINUE"

    CloudArchSaveFeedback().invoke({"feedback": {"status": "REVISION REQUIRED", "data": ["fix the WAF placement"]}}, {})

    second = loop_control.invoke({"required": required, "max_iterations": 2}, {})
    assert second == {"verdict": "STOP", "reason": "MAX_ITERATIONS"}


def test_process_pipeline_approves_after_both_reviewers_write_to_their_own_channel():
    ProcessReset().invoke({}, {})

    doc = {
        "process_name": "Vendor Onboarding",
        "process_steps": [
            {"step_name": "KYC Check", "responsible_party": "Compliance", "dependencies": []},
            {"step_name": "Contract Approval", "responsible_party": "Legal", "dependencies": ["KYC Check"]},
        ],
    }
    persist_result = PersistFinalJsonCodedTool().invoke({"json_content": doc}, {})
    assert persist_result.startswith("SUCCESS:")

    save_feedback = ProcessSaveFeedback()
    # Both reviewers write feedback in the same pass -- on a single shared
    # mailbox this would be a lost-write race; per-channel mailboxes avoid it.
    save_feedback.invoke({"channel": "compliance", "feedback": {"status": "COMPLIANCE APPROVED", "notes": "ok"}}, {})
    save_feedback.invoke({"channel": "simulation", "feedback": {"status": "SIMULATION_ALL_APPROVED", "notes": "ok"}}, {})

    verdict = ProcessLoopControl().invoke(
        {"required": {"compliance_status": "APPROVED", "simulation_status": "APPROVED"}, "max_iterations": 2}, {}
    )
    assert verdict == {"verdict": "STOP", "reason": "APPROVED"}
    assert LoadMasterProcessJsonCodedTool().invoke({}, {})["process_name"] == "Vendor Onboarding"


def test_process_pipeline_continues_if_only_one_reviewer_has_approved():
    ProcessReset().invoke({}, {})
    ProcessSaveFeedback().invoke({"channel": "compliance", "feedback": {"status": "COMPLIANCE APPROVED", "notes": "ok"}}, {})
    # simulation channel never approved

    verdict = ProcessLoopControl().invoke(
        {"required": {"compliance_status": "APPROVED", "simulation_status": "APPROVED"}, "max_iterations": 2}, {}
    )
    assert verdict["verdict"] == "CONTINUE"
