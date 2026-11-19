import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_interface.schema.itsm_json import (
    load_full_itsm_context,
    load_itsm_template,
    load_master_itsm_json,
    persist_final_itsm_json,
    validate_itsm_json,
)


class LoadMasterItsmJsonCodedTool(CodedTool):
    """Loads the existing ITSM process document JSON baseline, or the
    empty template if none exists yet. ALWAYS returns a valid object --
    never None."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_master_itsm_json()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class LoadFullItsmContextCodedTool(CodedTool):
    """Same content as LoadMasterItsmJsonCodedTool -- kept as a separate
    class for the consultant/reviewer/scenario-tester agents, mirroring
    process_interface's own load_full_itsm_context name."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_full_itsm_context()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class LoadItsmTemplateCodedTool(CodedTool):
    """Loads the empty ITSM process document JSON schema template, for
    completeness checks."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_itsm_template()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class ValidateItsmJsonCodedTool(CodedTool):
    """Validates an ITSM process document JSON object against the
    required structural rules."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return validate_itsm_json(args.get("json_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class PersistFinalItsmJsonCodedTool(CodedTool):
    """Validates and writes the final ITSM process document JSON to
    output/itsm_data.json.

    NOTE: this is called mid-loop (by ITSM_Agent, on any iteration where
    it actually changed something) -- NOT only once at the true end of a
    run -- so it must NOT release the pipeline lock here; see
    doc_generation_tool.py's GenerateItsmDocumentCodedTool, which is this
    pipeline's actual last step, for where that happens instead."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return persist_final_itsm_json(args.get("json_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
