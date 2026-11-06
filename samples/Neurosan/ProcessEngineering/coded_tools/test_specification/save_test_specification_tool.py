"""CodedTool: persist a structured test specification.

Logic lives in process_toolkit.test_specification.test_specification
(shared with the ADK port); this is just the neuro-san wrapper threading
sly_data through as the session-local cache.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.test_specification.test_specification import save_test_specification


class SaveTestSpecificationCodedTool(CodedTool):
    """Persists a test specification JSON object to disk."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        specification = args.get("specification")
        if not isinstance(specification, dict):
            return "ERROR: specification must be a JSON object."
        return save_test_specification(specification, sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
