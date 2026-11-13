import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.schema.togaf_json import (
    load_master_togaf_json,
    load_togaf_template,
    load_full_togaf_context,
    persist_final_togaf_json,
    validate_togaf_json,
)


class LoadMasterTogafJsonCodedTool(CodedTool):
    """Loads the existing TOGAF JSON baseline, or the empty template if
    none exists yet. ALWAYS returns a valid object -- never None."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_master_togaf_json()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class LoadTogafTemplateCodedTool(CodedTool):
    """Loads the empty TOGAF JSON template, for completeness checks."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_togaf_template()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class LoadFullTogafContextCodedTool(CodedTool):
    """Loads the existing TOGAF JSON baseline, pinned to the TOGAF schema
    (not auto-detected), for the scenario-tester agent."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_full_togaf_context()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class ValidateTogafJsonCodedTool(CodedTool):
    """Validates a TOGAF JSON object against the minimal structural rules
    (document_metadata required fields, requirement id/acceptance-criteria
    cross-field check)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return validate_togaf_json(args.get("json_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class PersistFinalTogafJsonCodedTool(CodedTool):
    """Validates and writes the final TOGAF JSON to output/togaf_data.json.

    NOTE: this is called mid-loop (by TOGAF_Agent, on any iteration where
    it actually changed something) -- NOT only once at the true end of a
    run -- so it must NOT release the pipeline lock here; see
    doc_generation_tool.py's GenerateTogafDocumentCodedTool, which is this
    pipeline's actual last step, for where that happens instead."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return persist_final_togaf_json(args.get("json_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
