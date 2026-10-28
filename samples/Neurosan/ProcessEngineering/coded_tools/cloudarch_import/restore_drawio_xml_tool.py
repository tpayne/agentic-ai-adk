"""CodedTool: persist an already-complete cloud architecture diagram's raw
XML VERBATIM -- as opposed to cloudarch.hocon's own save_drawio_structured
(coded_tools/cloudarch/save_drawio_structured_tool.py's
SaveDrawioStructuredCodedTool), which BUILDS the XML from structured
zones/components/edges via the layout engine. This one is for
CloudArch_Import_Agent's own literal-restore case: the content already IS
valid drawio/mxGraph XML (e.g. a cloudarch_drawio.xml re-attached after
being downloaded earlier), so there is nothing to build -- just the same
validate-and-persist save_drawio_xml already does for every other save
path. Lives directly under coded_tools/cloudarch_import/ (not a shim
re-exporting from elsewhere) since CloudArch_Import_Agent is this class's
only caller -- see coded_tools/process_subprocess_regenerate/
subprocess_tool.py's own docstring for why every OTHER tool this agent
uses (load_directory_context, load_drawio) needs a shim here instead.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.drawio_persistence import save_drawio_xml


class RestoreDrawioXmlCodedTool(CodedTool):
    """Persists `xml_content` verbatim as output/cloudarch_drawio.xml --
    save_drawio_xml itself already validates it's well-formed XML and
    handles the unchanged-file no-op case."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        xml_content = args.get("xml_content")
        if not isinstance(xml_content, str) or not xml_content.strip():
            return {"status": "ERROR", "error": "xml_content is required and must be a non-empty string."}
        return save_drawio_xml(xml_content)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
