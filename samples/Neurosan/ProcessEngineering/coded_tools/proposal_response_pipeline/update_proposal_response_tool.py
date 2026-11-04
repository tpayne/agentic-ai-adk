"""CodedTool: apply a targeted patch to the saved proposal response.

Logic lives in process_toolkit.proposal_response.proposal_response
(shared with the ADK port); this is just the neuro-san wrapper threading
sly_data through as the session-local cache. Used by Proposal_Response_
Reviewer_Agent to apply corrections it finds during a quality audit,
when the user's own request explicitly asked for fixes.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.proposal_response.proposal_response import update_proposal_response


class UpdateProposalResponseCodedTool(CodedTool):
    """Shallow-merges a patch onto the saved proposal response and
    re-persists it."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        patch = args.get("patch")
        if not isinstance(patch, dict):
            return "ERROR: patch must be a JSON object."
        return update_proposal_response(patch, sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
