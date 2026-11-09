"""Persists a SAFe WSJF backlog and renders its XLSX workbook."""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.portfolio_backlog.portfolio_backlog import save_portfolio_backlog


class SavePortfolioBacklogCodedTool(CodedTool):
    """Saves the structured backlog JSON and its template-based workbook."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        backlog = args.get("backlog")
        if not isinstance(backlog, dict):
            return "ERROR: backlog must be a JSON object."
        return save_portfolio_backlog(backlog, sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
