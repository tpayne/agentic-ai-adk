import base64
import os

from process_interface import _artifacts
from process_toolkit import paths


class TestMaterialize:
    def test_decodes_and_writes_to_output_path(self):
        content = b"real bytes, not a placeholder"
        documents = [{"filename": "report.docx", "base64": base64.b64encode(content).decode("ascii")}]

        written = _artifacts.materialize(documents)

        assert written == [paths.output_path("report.docx")]
        with open(written[0], "rb") as f:
            assert f.read() == content

    def test_writes_multiple_documents_in_order(self):
        documents = [
            {"filename": "a.docx", "base64": base64.b64encode(b"A").decode("ascii")},
            {"filename": "b.docx", "base64": base64.b64encode(b"B").decode("ascii")},
        ]
        written = _artifacts.materialize(documents)
        assert [os.path.basename(p) for p in written] == ["a.docx", "b.docx"]


class TestMaterializeOne:
    def test_none_input_returns_none_without_writing_anything(self):
        assert _artifacts.materialize_one(None) is None

    def test_single_document_materializes_and_returns_its_path(self):
        content = b"diagram bytes"
        doc = {"filename": "diagram.png", "base64": base64.b64encode(content).decode("ascii")}
        result = _artifacts.materialize_one(doc)
        assert result == paths.output_path("diagram.png")
        with open(result, "rb") as f:
            assert f.read() == content
