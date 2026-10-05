"""CodedTool: persist a structured requirements summary.

Ported from the ADK sample's save_requirements_summary (utils.py). Single
shared slot on disk (output/requirements_summary.json), same as the ADK
original -- this is the deliberate cross-process reuse mechanism a later
"use the saved requirements summary" request relies on. sly_data is also
written (the neuro-san analogue of ADK's tool_context.state) so that
LoadRequirementsSummaryCodedTool can prefer this session's own save over
whatever a different concurrent session most recently overwrote the shared
file with -- same reasoning as the ADK original's per-session caching.
"""

import asyncio
import json
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.paths import output_path

SLY_DATA_KEY = "requirements_summary"


class SaveRequirementsSummaryCodedTool(CodedTool):
    """Persists a requirements summary JSON object to disk."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        summary = args.get("summary")
        if not isinstance(summary, dict):
            return "ERROR: summary must be a JSON object."

        path = output_path("requirements_summary.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            sly_data[SLY_DATA_KEY] = summary
            return f"SUCCESS: Requirements summary persisted to {path}"
        except Exception as e:
            return f"ERROR: Could not save requirements summary: {e}"

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
