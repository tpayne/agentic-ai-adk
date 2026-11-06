"""CodedTool: load a previously-saved test specification.

Logic lives in process_toolkit.test_specification.test_specification
(shared with the ADK port); this is just the neuro-san wrapper threading
sly_data through as the session-local cache.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.test_specification.test_specification import load_test_specification


class LoadTestSpecificationCodedTool(CodedTool):
    """Loads the most relevant test specification -- this session's own,
    or the shared on-disk one."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_test_specification(sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
