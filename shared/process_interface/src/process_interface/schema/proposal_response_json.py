"""Always-local re-export -- pure computation, no disk I/O of its own
(the actual save/load lives in proposal_response/proposal_response.py, a
separate switchable module)."""

from process_toolkit.schema.proposal_response_json import (
    load_proposal_response_template,
    validate_proposal_response,
)

__all__ = ["load_proposal_response_template", "validate_proposal_response"]
