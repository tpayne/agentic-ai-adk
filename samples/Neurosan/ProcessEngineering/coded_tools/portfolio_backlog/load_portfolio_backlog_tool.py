"""Loads the saved Enterprise Agile Portfolio Backlog."""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.portfolio_backlog.portfolio_backlog import load_portfolio_backlog


class LoadPortfolioBacklogCodedTool(CodedTool):
    """Loads the existing backlog JSON from session state or the output directory."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_portfolio_backlog(sly_data)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
