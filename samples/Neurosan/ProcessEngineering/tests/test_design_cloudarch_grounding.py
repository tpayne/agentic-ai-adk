"""Regression coverage for a real production bug: asked to "create an HLD
based on this cloud architecture" (an uploaded drawio diagram with no
stated business purpose, just infrastructure), Design_Doc_Agent fabricated
an entirely unrelated business domain ("Global Inventory & Order
Management System") out of nothing -- confirmed via a live trace
(output/logs/web_sessions/<session>/agent_thinking/
Process_Architect_Orchestrator.__design`) showing the orchestrator DID pass
accurate infrastructure detail through, and Design_Doc_Agent still invented
a business narrative to fill business_context/document_metadata.

Two independent problems, fixed together here:
1. Design_Doc_Analysis_Agent had no tool at all to read an existing cloud
   architecture diagram -- `load_drawio` is now wired in, following the
   same opt-in, explicitly-requested cross-pipeline read already used by
   CloudArch_Consultant_Agent/CloudArch_FinOps_Agent/etc. (design and
   cloud-architecture stay isolated by default; a diagram is only loaded
   when the request actually references one).
2. Even with accurate infrastructure detail in hand, nothing stopped
   Design_Doc_Agent inventing a business domain to satisfy the schema's
   business_context/document_metadata fields. `business_purpose_stated`
   (set by Design_Doc_Analysis_Agent) plus the new "INFRASTRUCTURE-ONLY
   INPUT" instructions block this -- the business_context.purpose must
   explicitly say no business purpose was stated instead of fabricating one.
"""

from pathlib import Path

from coded_tools.cloudarch.load_drawio_tool import LoadDrawioCodedTool as CanonicalLoadDrawio
from coded_tools.design.load_drawio_tool import LoadDrawioCodedTool

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESIGN_HOCON = PROJECT_ROOT / "registries" / "design.hocon"


def test_design_load_drawio_shim_reexports_the_canonical_class():
    # Imported from the network's OWN shim path -- the same import
    # neuro-san's own resolver performs at runtime -- and asserted `is`
    # (identity, not just equality) the canonical class.
    assert LoadDrawioCodedTool is CanonicalLoadDrawio


def test_design_doc_analysis_agent_can_load_the_existing_diagram():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert '"load_directory_context", "load_requirements_summary", "load_drawio", "save_iteration_feedback"' in text
    assert '"name": "load_drawio"' in text
    assert "load_drawio_tool.LoadDrawioCodedTool" in text


def test_design_doc_analysis_agent_tracks_whether_a_business_purpose_was_stated():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert "business_purpose_stated" in text
    assert "NEVER set this true by inferring or guessing" in text


def test_design_doc_agent_refuses_to_fabricate_a_business_domain():
    text = DESIGN_HOCON.read_text(encoding="utf-8")
    assert "INFRASTRUCTURE-ONLY INPUT" in text
    assert "do NOT invent one (no" in text
    assert "business_context.purpose: state plainly that no business purpose was provided" in text
