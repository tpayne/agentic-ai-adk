"""Wiring coverage for the two new standalone, on-demand requirements
networks: registries/requirements_reviewer.hocon (SRS/ISO-29148 quality
audit of the saved requirements) and registries/requirements_simulation_query.hocon
(fresh completeness/gap analysis beyond what extraction already flagged).
Both mirror registries/requirements_consultant.hocon's exact shape --
single tool, no save/creation tool, no loop_control/iteration_feedback
machinery -- deliberately NOT the CloudArch_Reviewer_Agent/Compliance_Agent
pattern (not a pipeline-internal auto-revision gate).
"""

from pathlib import Path

from coded_tools.requirements_summary.load_requirements_summary_tool import (
    LoadRequirementsSummaryCodedTool as CanonicalLoadRequirementsSummary,
)
from coded_tools.requirements_reviewer.load_requirements_summary_tool import (
    LoadRequirementsSummaryCodedTool as ReviewerLoadRequirementsSummary,
)
from coded_tools.requirements_simulation_query.load_requirements_summary_tool import (
    LoadRequirementsSummaryCodedTool as SimulationQueryLoadRequirementsSummary,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_HOCON = PROJECT_ROOT / "registries" / "manifest.hocon"
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"


def test_shims_reexport_the_canonical_load_requirements_summary_class():
    assert ReviewerLoadRequirementsSummary is CanonicalLoadRequirementsSummary
    assert SimulationQueryLoadRequirementsSummary is CanonicalLoadRequirementsSummary


def test_manifest_registers_both_new_networks():
    text = MANIFEST_HOCON.read_text(encoding="utf-8")
    assert '"requirements_reviewer.hocon"' in text
    assert '"requirements_simulation_query.hocon"' in text


def test_router_references_both_new_networks():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "Requirements_Reviewer_Agent" in text
    assert "Requirements_Simulation_Query_Agent" in text
    assert '"/requirements_reviewer"' in text
    assert '"/requirements_simulation_query"' in text


def test_router_disambiguates_review_from_the_existing_consultant():
    # The one real design risk in this feature: both new agents overlap
    # in phrasing with the existing Consultant. Lock in that the
    # precedence rule is actually present, not just implied.
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "PRECEDENCE vs. 4d" in text
    assert text.count("PRECEDENCE vs. 4d") == 2  # once in 3f, once in 4e


def test_router_multi_intent_priority_mentions_both_new_agents():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "requirements completeness -> Requirements_Simulation_Query_Agent" in text
    assert "requirements quality -> Requirements_Reviewer_Agent" in text
