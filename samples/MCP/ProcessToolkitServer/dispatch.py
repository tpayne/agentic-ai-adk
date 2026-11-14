"""Per-domain lookup tables for server.py's generic, schema_type-dispatched
tools. Keeps the domain-specific wiring (which process_toolkit function
backs "load template" for togaf vs. requirements, which domains have a
native persist_final vs. only a bare save_*, which have a document-variant
knob, which have a whole-document diagram) out of the tool functions
themselves and out of process_toolkit (which stays framework/MCP-agnostic).

Every entry's `load_context`/`persist` callables already take no `state`
argument (or default it to None) -- this server is disk-only, scoped per
request via process_toolkit.paths.use_session, never an ADK ToolContext.state
or neuro-san sly_data object, since it has no such concept of its own.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from process_toolkit.docgen.generation import create_standard_doc_from_file
from process_toolkit.proposal_response.proposal_response import (
    load_proposal_response,
    save_proposal_response,
)
from process_toolkit.requirements_summary.requirements_summary import (
    load_requirements_summary,
    save_requirements_summary,
)
from process_toolkit.schema.design_json import (
    load_design_template,
    load_full_design_context,
    persist_final_design_json,
    validate_design_json,
)
from process_toolkit.schema.process_json import (
    load_process_template,
    load_full_process_context,
    persist_final_json as persist_final_process_json,
    validate_process_json,
)
from process_toolkit.schema.proposal_response_json import (
    load_proposal_response_template,
    validate_proposal_response,
)
from process_toolkit.schema.requirements_json import (
    load_requirements_summary_template,
    validate_requirements_summary,
)
from process_toolkit.schema.test_specification_json import (
    load_test_specification_template,
    validate_test_specification,
)
from process_toolkit.schema.togaf_json import (
    load_full_togaf_context,
    load_togaf_template,
    persist_final_togaf_json,
    validate_togaf_json,
)
from process_toolkit.test_specification.test_specification import (
    load_test_specification,
    save_test_specification,
)


def _validate_then_save(validate_fn: Callable[[Any], dict], save_fn: Callable[[dict], str]) -> Callable[[dict], str]:
    """Composes a `persist` step for the three domains whose own save_*
    function performs no validation at all (requirements, proposal_response,
    test_specification) -- gives every domain the same "validate, then
    persist only if valid" contract at this server's boundary without
    changing process_toolkit's own, intentionally-asymmetric behavior."""

    def _persist(data: dict) -> str:
        validation = validate_fn(data)
        if not validation.get("valid"):
            return f"ERROR: JSON failed validation: {validation.get('issues')}"
        return save_fn(data)

    return _persist


@dataclass(frozen=True)
class DomainOps:
    load_template: Callable[[], dict]
    load_context: Callable[[], dict]
    validate: Optional[Callable[[Any], dict]]
    persist: Callable[[dict], str]
    persist_is_native: bool  # False => persist is our own validate-then-save composition, not process_toolkit's
    doc_variant_kwarg: Optional[str]  # e.g. "design_variant", or None if this schema_type takes no variant
    has_diagram: bool  # whether generate_document (via generate_clean_diagram) should also be tried for a flow diagram


DOMAINS: dict[str, DomainOps] = {
    "design": DomainOps(
        load_template=load_design_template,
        load_context=load_full_design_context,
        validate=validate_design_json,
        persist=persist_final_design_json,
        persist_is_native=True,
        doc_variant_kwarg="design_variant",
        has_diagram=True,
    ),
    "togaf": DomainOps(
        load_template=load_togaf_template,
        load_context=load_full_togaf_context,
        validate=validate_togaf_json,
        persist=persist_final_togaf_json,
        persist_is_native=True,
        doc_variant_kwarg="togaf_variant",
        has_diagram=False,  # TOGAF's diagrams are per-section, rendered inline by the document build itself
    ),
    "process": DomainOps(
        load_template=load_process_template,
        load_context=load_full_process_context,
        validate=validate_process_json,
        persist=persist_final_process_json,
        persist_is_native=True,
        doc_variant_kwarg=None,
        has_diagram=True,
    ),
    "requirements": DomainOps(
        load_template=load_requirements_summary_template,
        load_context=lambda: load_requirements_summary(None),
        validate=validate_requirements_summary,
        persist=_validate_then_save(validate_requirements_summary, lambda data: save_requirements_summary(data, None)),
        persist_is_native=False,
        doc_variant_kwarg=None,
        has_diagram=False,
    ),
    "proposal_response": DomainOps(
        load_template=load_proposal_response_template,
        load_context=lambda: load_proposal_response(None),
        validate=validate_proposal_response,
        persist=_validate_then_save(validate_proposal_response, lambda data: save_proposal_response(data, None)),
        persist_is_native=False,
        doc_variant_kwarg=None,
        has_diagram=False,
    ),
    "test_specification": DomainOps(
        load_template=load_test_specification_template,
        load_context=lambda: load_test_specification(None),
        validate=validate_test_specification,
        persist=_validate_then_save(validate_test_specification, lambda data: save_test_specification(data, None)),
        persist_is_native=False,
        doc_variant_kwarg=None,
        has_diagram=False,
    ),
}


def generate_document_for(schema_type: str, process_name: str, variant: Optional[str]) -> str:
    """Thin pass-through to the shared dispatcher in docgen/generation.py --
    kept here (rather than inlined in server.py) only so every domain's
    quirk (which variant kwarg name applies) is resolved in one place."""
    ops = DOMAINS[schema_type]
    kwargs: dict[str, Any] = {}
    if ops.doc_variant_kwarg and variant:
        kwargs[ops.doc_variant_kwarg] = variant
    return create_standard_doc_from_file(process_name=process_name, schema_type=schema_type, **kwargs)
