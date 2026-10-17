import os
import tempfile
from email.message import EmailMessage
from pathlib import Path

from process_toolkit.ingestion.extractors import (
    load_directory_context, DIRECTORY_CONTEXT_EXTRACTORS, _extract_msg_file,
    extract_attachment_text,
)


def test_missing_directory_returns_not_found():
    with tempfile.TemporaryDirectory() as d:
        missing = str(Path(d) / "does-not-exist")
        result = load_directory_context(missing)
    assert result["status"] == "NOT_FOUND"


def test_extracts_txt_and_docx_and_skips_legacy_doc():
    import docx

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "notes.txt").write_text(
            "Vendor onboarding requires KYC checks and a 3-day SLA."
        )

        doc = docx.Document()
        doc.add_paragraph("Stakeholders: Procurement Lead, Compliance Officer.")
        doc.save(str(Path(d) / "stakeholders.docx"))

        (Path(d) / "legacy.doc").write_text("ignored -- old binary format")

        result = load_directory_context(d)

    assert result["status"] == "OK"
    assert sorted(result["files_processed"]) == ["notes.txt", "stakeholders.docx"]
    assert "KYC checks" in result["combined_text"]
    assert "Procurement Lead" in result["combined_text"]
    assert "=== notes.txt ===" in result["combined_text"]

    skipped = {entry["file"]: entry["reason"] for entry in result["files_skipped"]}
    assert "legacy.doc" in skipped
    assert "re-save as .docx" in skipped["legacy.doc"]


def test_docx_table_text_is_extracted_not_silently_dropped():
    import docx

    with tempfile.TemporaryDirectory() as d:
        doc = docx.Document()
        doc.add_paragraph("Requirements register:")
        table = doc.add_table(rows=2, cols=2)
        table.rows[0].cells[0].text = "REQ-1"
        table.rows[0].cells[1].text = "Support SSO login"
        table.rows[1].cells[0].text = "REQ-2"
        table.rows[1].cells[1].text = "Encrypt data at rest"
        doc.save(str(Path(d) / "requirements.docx"))

        result = load_directory_context(d)

    assert result["status"] == "OK"
    assert "Support SSO login" in result["combined_text"]
    assert "Encrypt data at rest" in result["combined_text"]


def test_unsupported_extension_is_skipped_not_fatal():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "readme.txt").write_text("real content")
        (Path(d) / "image.jpg").write_bytes(b"\xff\xd8\xff\xe0not-a-real-jpeg")

        result = load_directory_context(d)

    assert result["status"] == "OK"
    assert result["files_processed"] == ["readme.txt"]
    skipped_files = [entry["file"] for entry in result["files_skipped"]]
    assert "image.jpg" in skipped_files


def test_excel_xlsx_renders_sheet_as_text():
    import pandas as pd

    with tempfile.TemporaryDirectory() as d:
        df = pd.DataFrame({"Step": ["Receive PO", "Validate budget"], "Owner": ["Ops", "Finance"]})
        xlsx_path = Path(d) / "steps.xlsx"
        df.to_excel(xlsx_path, index=False, sheet_name="Process")

        result = load_directory_context(d)

    assert result["status"] == "OK"
    assert result["files_processed"] == ["steps.xlsx"]
    assert "Receive PO" in result["combined_text"]
    assert "Validate budget" in result["combined_text"]
    assert "[Sheet: Process]" in result["combined_text"]


def test_eml_extraction_returns_subject_and_body():
    with tempfile.TemporaryDirectory() as d:
        msg = EmailMessage()
        msg["Subject"] = "Q3 onboarding requirements"
        msg["From"] = "ops@example.com"
        msg["To"] = "architecture@example.com"
        msg.set_content("All new vendors must complete KYC within 5 business days.")

        eml_path = Path(d) / "requirements.eml"
        eml_path.write_bytes(bytes(msg))

        result = load_directory_context(d)

    assert result["status"] == "OK"
    assert result["files_processed"] == ["requirements.eml"]
    assert "Q3 onboarding requirements" in result["combined_text"]
    assert "KYC within 5 business days" in result["combined_text"]


def test_blank_pdf_has_no_extractable_text_and_is_skipped():
    from pypdf import PdfWriter

    with tempfile.TemporaryDirectory() as d:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        pdf_path = Path(d) / "blank.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = load_directory_context(d)

    assert result["status"] == "OK"
    assert result["files_processed"] == []
    skipped = {entry["file"]: entry["reason"] for entry in result["files_skipped"]}
    assert skipped.get("blank.pdf") == "no extractable text"


def test_msg_extension_is_wired_to_its_extractor():
    # A full positive-content test would require fabricating a valid
    # OLE-format .msg file, which extract_msg (read-only) provides no
    # authoring API for. Covering the wiring and the graceful-failure
    # path (a malformed .msg must be skipped, not crash the directory
    # read) is the practical level of coverage here.
    assert DIRECTORY_CONTEXT_EXTRACTORS[".msg"] is _extract_msg_file

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "broken.msg").write_bytes(b"not a real OLE msg file")
        result = load_directory_context(d)

    assert result["status"] == "OK"
    assert result["files_processed"] == []
    skipped = {entry["file"]: entry["reason"] for entry in result["files_skipped"]}
    assert "broken.msg" in skipped
    assert "failed to read" in skipped["broken.msg"]


def test_combined_text_is_truncated_past_the_configured_limit():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "big.txt").write_text("x" * 500)

        result = load_directory_context(d, max_chars=100)

    assert result["status"] == "OK"
    assert result.get("truncated") is True
    assert "truncated at 100 characters" in result["combined_text"]


class TestExtractAttachmentText:
    """extract_attachment_text -- the single-uploaded-file counterpart to
    load_directory_context, used by a chat turn's file-attachment support.
    Reuses the exact same DIRECTORY_CONTEXT_EXTRACTORS, just against raw
    in-memory bytes instead of an on-disk directory."""

    def test_extracts_txt_bytes(self):
        result = extract_attachment_text("notes.txt", b"Vendor onboarding requires a 3-day SLA.")
        assert result == {"status": "OK", "name": "notes.txt", "text": "Vendor onboarding requires a 3-day SLA."}

    def test_extracts_pdf_bytes(self):
        from pypdf import PdfWriter
        import io

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)

        result = extract_attachment_text("blank.pdf", buf.getvalue())
        # A blank page has no text layer -- confirms the PDF extractor
        # path actually ran (no exception/UNSUPPORTED-for-wrong-reason),
        # landing on the same "no extractable text" outcome
        # load_directory_context's own PDF test would hit for a blank page.
        assert result["status"] == "UNSUPPORTED"
        assert result["name"] == "blank.pdf"
        assert result["reason"] == "no extractable text"

    def test_image_extension_has_no_extractor(self):
        result = extract_attachment_text("diagram.png", b"\x89PNG\r\n\x1a\nnot a real png")
        assert result["status"] == "UNSUPPORTED"
        assert result["name"] == "diagram.png"
        assert "not readable as text" in result["reason"]

    def test_legacy_doc_extension_gets_a_specific_reason(self):
        result = extract_attachment_text("old.doc", b"ignored -- old binary format")
        assert result["status"] == "UNSUPPORTED"
        assert "re-save as .docx" in result["reason"]

    def test_malformed_file_fails_gracefully_not_with_an_exception(self):
        result = extract_attachment_text("broken.pdf", b"not a real pdf")
        assert result["status"] == "UNSUPPORTED"
        assert "failed to read" in result["reason"] or "no extractable text" in result["reason"]

    def test_text_is_truncated_past_the_configured_limit(self):
        result = extract_attachment_text("big.txt", b"x" * 500, max_chars=100)
        assert result["status"] == "OK"
        assert result.get("truncated") is True
        assert "truncated at 100 characters" in result["text"]
        assert len(result["text"]) < 500

    def test_temp_file_is_cleaned_up_after_extraction(self):
        import glob
        import tempfile as tempfile_module

        before = set(glob.glob(os.path.join(tempfile_module.gettempdir(), "*.txt")))
        extract_attachment_text("notes.txt", b"hello")
        after = set(glob.glob(os.path.join(tempfile_module.gettempdir(), "*.txt")))
        assert after - before == set()
