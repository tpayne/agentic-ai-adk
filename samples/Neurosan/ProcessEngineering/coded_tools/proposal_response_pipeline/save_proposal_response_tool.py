"""CodedTool: persist a drafted proposal response.

Logic lives in process_toolkit.proposal_response.proposal_response
(shared with the ADK port); this is just the neuro-san wrapper threading
sly_data through as the session-local cache. Canonical implementation --
proposal_response.json is only ever written by this one network, unlike
requirements_summary.json (which also has a dedicated
requirements_summary network re-exported by many others).
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.proposal_response.proposal_response import (
    save_proposal_response,
    STATE_KEY as SLY_DATA_KEY,
)


class SaveProposalResponseCodedTool(CodedTool):
    """Persists a drafted proposal response JSON object to disk."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        response = args.get("response")
        if not isinstance(response, dict):
            return "ERROR: response must be a JSON object."
        return save_proposal_response(response, sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
