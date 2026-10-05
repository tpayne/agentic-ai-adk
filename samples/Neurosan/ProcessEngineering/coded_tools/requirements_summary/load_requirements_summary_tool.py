"""CodedTool: load a previously-saved requirements summary.

Ported from the ADK sample's load_requirements_summary (utils.py). Prefers
this session's own sly_data copy (see save_requirements_summary_tool.py)
over the shared output/requirements_summary.json file, so that a session
asking "what did I just save" never reads back a different concurrent
session's overwrite -- falling back to the shared file only when this
session never saved one itself (e.g. explicitly reusing an earlier run's
summary).
"""

import asyncio
import json
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.paths import output_path
from coded_tools.requirements_summary.save_requirements_summary_tool import SLY_DATA_KEY


class LoadRequirementsSummaryCodedTool(CodedTool):
    """Loads the most relevant requirements summary -- this session's own,
    or the shared on-disk one."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        session_summary = sly_data.get(SLY_DATA_KEY)
        if isinstance(session_summary, dict):
            result = dict(session_summary)
            result.setdefault("status", "OK")
            return result

        path = output_path("requirements_summary.json")
        if not os.path.exists(path):
            return {"status": "NOT_FOUND"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                summary = json.load(f)
            if isinstance(summary, dict):
                summary.setdefault("status", "OK")
            return summary
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
