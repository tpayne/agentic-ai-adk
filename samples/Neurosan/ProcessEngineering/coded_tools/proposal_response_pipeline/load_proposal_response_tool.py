"""CodedTool: load a previously-saved proposal response.

Logic lives in process_toolkit.proposal_response.proposal_response
(shared with the ADK port); this is just the neuro-san wrapper threading
sly_data through as the session-local cache. Canonical implementation --
proposal_response.json is only ever written by this one network, same as
save_proposal_response_tool.py's own role here.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.proposal_response.proposal_response import load_proposal_response


class LoadProposalResponseCodedTool(CodedTool):
    """Loads the most relevant proposal response -- this session's own,
    or the shared on-disk one."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_proposal_response(sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
