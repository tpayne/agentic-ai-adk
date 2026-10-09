import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.generation import create_standard_doc_from_file


class GenerateDesignDocumentCodedTool(CodedTool):
    """Generates a structured, ISO-formatted Word document from the
    current design-document JSON. "process_name" is an optional fallback
    title -- the design JSON's own document_metadata.title/system_name
    takes precedence."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        fallback_name = args.get("process_name") or "Design"
        return create_standard_doc_from_file(fallback_name, schema_type="design")

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
