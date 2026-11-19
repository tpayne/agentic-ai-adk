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
from process_toolkit.schema.itsm_json import (
    load_full_itsm_context,
    load_itsm_template,
    persist_final_itsm_json,
    validate_itsm_json,
)
from process_toolkit.test_specification.test_specification import (
    load_test_specification,
    save_test_specification,
)


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
    "itsm": DomainOps(
        load_template=load_itsm_template,
        load_context=load_full_itsm_context,
        validate=validate_itsm_json,
        persist=persist_final_itsm_json,
        persist_is_native=True,
        doc_variant_kwarg=None,
        has_diagram=False,  # ITSM's diagrams are per-process, rendered inline by the document build itself
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
        # Plain save, not validate-then-save: process_toolkit's own
        # save_requirements_summary is INTENTIONALLY zero-validation (its
        # own docstring says so -- callers can save an in-progress draft
        # that doesn't yet pass validate_requirements_summary's structural
        # checks). This server now backs process_interface's MCP mode as
        # well as third-party MCP clients, and process_interface needs
        # exact behavioral parity with local mode -- forcing validation
        # here that local mode doesn't have would make MCP mode strictly
        # stricter, silently breaking saves that work fine locally.
        # validate_json remains available as its own, separate tool call.
        persist=lambda data: save_requirements_summary(data, None),
        persist_is_native=True,
        doc_variant_kwarg=None,
        has_diagram=False,
    ),
    "proposal_response": DomainOps(
        load_template=load_proposal_response_template,
        load_context=lambda: load_proposal_response(None),
        validate=validate_proposal_response,
        persist=lambda data: save_proposal_response(data, None),
        persist_is_native=True,
        doc_variant_kwarg=None,
        has_diagram=False,
    ),
    "test_specification": DomainOps(
        load_template=load_test_specification_template,
        load_context=lambda: load_test_specification(None),
        validate=validate_test_specification,
        persist=lambda data: save_test_specification(data, None),
        persist_is_native=True,
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
