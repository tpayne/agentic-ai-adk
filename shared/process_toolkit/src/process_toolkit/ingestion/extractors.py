"""Per-extension text extractors for load_directory_context.

Ported verbatim from the ADK sample's process_agents/common/utils.py
(_extract_*_file + _DIRECTORY_CONTEXT_EXTRACTORS) -- pure Python, nothing
framework-specific, so the logic carries over unchanged.
"""

import os
import tempfile


def _extract_txt_file(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def _extract_xml_file(path: str) -> str:
    # Read as raw markup, not parsed/re-serialized -- an uploaded XML file
    # here is typically a structured process/architecture export (a BPMN
    # process definition, a drawio/mxGraph diagram, a Visio export) being
    # offered as source material, and an LLM generally understands XML
    # structure directly from the raw tags at least as well as from any
    # text this module could derive from it, so this is the same
    # read-as-text approach as _extract_txt_file above, not a dedicated
    # parser.
    return _extract_txt_file(path)


def _extract_docx_file(path: str) -> str:
    import docx
    doc = docx.Document(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_pdf_file(path: str) -> str:
    # pypdf extracts embedded text only -- a scanned/image-only PDF with no
    # text layer yields empty strings per page (no OCR is attempted), which
    # load_directory_context surfaces as "no extractable text" rather than
    # silently pretending the file contributed content.
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p for p in pages if p.strip())


def _extract_eml_file(path: str) -> str:
    import email
    from email import policy
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default)

    header_lines = [
        f"{header}: {msg.get(header)}" for header in ("Subject", "From", "To", "Date")
        if msg.get(header)
    ]

    body = ""
    if msg.is_multipart():
        # Prefer the first real text/plain body part; a part that also
        # carries a filename is an attachment, not the message body, even
        # if its content type happens to be text/plain (e.g. a .txt
        # attachment) -- skip those.
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                body = part.get_content()
                break
    else:
        body = msg.get_content()

    return "\n".join(header_lines) + "\n\n" + (body or "")


def _extract_msg_file(path: str) -> str:
    import extract_msg
    msg = extract_msg.Message(path)
    try:
        header_lines = [
            f"{label}: {value}" for label, value in (
                ("Subject", msg.subject), ("From", msg.sender),
                ("To", msg.to), ("Date", msg.date),
            ) if value
        ]
        return "\n".join(header_lines) + "\n\n" + (msg.body or "")
    finally:
        msg.close()


_EXCEL_MAX_ROWS_PER_SHEET = 200


def _extract_excel_file(path: str) -> str:
    # .xls (legacy binary) needs xlrd, .xlsx (modern XML) needs openpyxl --
    # pandas picks the right engine automatically from the file extension,
    # as long as both packages are installed.
    import pandas as pd
    sheets = pd.read_excel(path, sheet_name=None)
    parts = []
    for sheet_name, df in sheets.items():
        truncated_df = df.head(_EXCEL_MAX_ROWS_PER_SHEET)
        note = ""
        if len(df) > _EXCEL_MAX_ROWS_PER_SHEET:
            note = f"\n... ({len(df) - _EXCEL_MAX_ROWS_PER_SHEET} more rows truncated)"
        parts.append(f"[Sheet: {sheet_name}]\n{truncated_df.to_string(index=False)}{note}")
    return "\n\n".join(parts)


# Legacy .doc (binary, pre-2007 Word) is deliberately absent -- python-docx
# only reads the modern .docx XML format. A .doc file is caught in
# load_directory_context and reported in files_skipped with a specific
# "re-save as .docx" reason, rather than silently falling through to
# "unsupported file type".
DIRECTORY_CONTEXT_EXTRACTORS = {
    ".txt": _extract_txt_file,
    ".md": _extract_txt_file,
    ".docx": _extract_docx_file,
    ".pdf": _extract_pdf_file,
    ".eml": _extract_eml_file,
    ".msg": _extract_msg_file,
    ".xls": _extract_excel_file,
    ".xlsx": _extract_excel_file,
    ".xml": _extract_xml_file,
}


def _agent_toolkit_root() -> "str | None":
    """The running agent project's own root directory (one level up from
    AGENT_TOOL_PATH, which every one of this suite's entry points --
    cli.py, `ns chat`, `ns run` -- sets to <project_root>/coded_tools
    before any CodedTool loads). Returns None if AGENT_TOOL_PATH isn't set
    (e.g. a unit test importing this module directly)."""
    agent_tool_path = os.environ.get("AGENT_TOOL_PATH")
    if not agent_tool_path:
        return None
    return os.path.dirname(os.path.abspath(agent_tool_path))


def load_directory_context(directory: str, max_chars: int = 150000) -> dict:
    """
    Reads every supported file directly inside `directory` (not recursive --
    only that directory's own files, not subdirectories) and returns their
    extracted text, concatenated and labeled by filename, for use as source
    material in a requirements-extraction step. Turning the returned text
    into a structured requirements JSON is the calling agent's own job via
    its instructions.

    Returns {"status": "NOT_FOUND", "directory": <resolved path>} if the
    directory doesn't exist. {"status": "ERROR", "directory": ...,
    "error": "..."} if `directory` resolves to the agent toolkit's own
    project root/tool path (see _agent_toolkit_root) -- an LLM-supplied
    directory argument that is relative, empty, or otherwise doesn't name
    a real source-document location (".", "", a bad guess after a NOT_FOUND)
    resolves right back to wherever the server process's cwd happens to be,
    which for every one of this project's entry points IS the project root;
    without this guard, that silently returns this project's OWN
    README/BUSINESS-CASES.md etc. as if they were genuine source material,
    with no error signal at all -- the agent then confidently "summarizes
    requirements" from the tool's own docs instead of what the user meant.
    Otherwise {"status": "OK", "directory": ..., "files_processed": [...],
    "files_skipped": [{"file":..., "reason":...}], "combined_text": "..."}.
    combined_text is capped at max_chars with a truncation note appended if
    exceeded, so a large directory can't blow out the model's context
    window.

    KNOWN GAP (prompt-injection exposure, not yet addressed): combined_text
    is surfaced to the LLM with no framing marking it as untrusted data.
    """
    resolved = os.path.abspath(directory)
    if not os.path.isdir(resolved):
        return {"status": "NOT_FOUND", "directory": resolved}

    toolkit_root = _agent_toolkit_root()
    if toolkit_root is not None and resolved == toolkit_root:
        return {
            "status": "ERROR",
            "directory": resolved,
            "error": (
                "This resolves to the agent toolkit's own project directory, not a "
                "source-document directory -- refusing to read it. The directory argument "
                "was likely relative, empty, or otherwise invalid rather than a real path "
                "to the user's source files."
            ),
        }

    try:
        entries = sorted(os.listdir(resolved))
    except Exception as e:
        return {"status": "ERROR", "directory": resolved, "error": str(e)}

    files_processed = []
    files_skipped = []
    sections = []

    for name in entries:
        full_path = os.path.join(resolved, name)
        if not os.path.isfile(full_path):
            continue

        ext = os.path.splitext(name)[1].lower()
        extractor = DIRECTORY_CONTEXT_EXTRACTORS.get(ext)
        if extractor is None:
            reason = (
                "legacy .doc (unsupported -- re-save as .docx)" if ext == ".doc"
                else f"unsupported file type '{ext or '(no extension)'}'"
            )
            files_skipped.append({"file": name, "reason": reason})
            continue

        try:
            text = (extractor(full_path) or "").strip()
        except Exception as e:
            files_skipped.append({"file": name, "reason": f"failed to read: {e}"})
            continue

        if not text:
            files_skipped.append({"file": name, "reason": "no extractable text"})
            continue

        files_processed.append(name)
        sections.append(f"=== {name} ===\n{text}")

    combined_text = "\n\n".join(sections)
    truncated = len(combined_text) > max_chars
    if truncated:
        combined_text = combined_text[:max_chars] + (
            f"\n\n[... truncated at {max_chars} characters ...]"
        )

    result = {
        "status": "OK",
        "directory": resolved,
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "combined_text": combined_text,
    }
    if truncated:
        result["truncated"] = True
    return result


def stage_attachments_to_directory(
    files: list, base_dir: "str | None" = None, directory: "str | None" = None,
) -> dict:
    """
    Writes this turn's attached files (raw bytes) to an on-disk
    directory, so an agent can read them through the EXACT SAME
    load_directory_context path a directory-context request already
    uses -- one well-tested file-reading implementation (with its own
    per-extension extractors, skip-tracking, truncation, and
    self-reference guard against the agent toolkit's own project root)
    instead of a second, parallel single-file extraction mechanism with
    its own separate result shape and error handling.

    `files`: [{"name": str, "data": bytes}, ...] -- the same shape
    cli.py's _parse_attachments/_ingest_attachments already produce.
    `directory`: an exact, caller-chosen path to stage into (e.g. a
    deterministic per-session directory cli.py computes once at
    ChatSession construction) -- created if missing; any FILES already
    in it are removed first, so a later turn's attachment set never
    mixes with an earlier one left behind in the same fixed path.
    Mutually exclusive with `base_dir` conceptually (if both are given,
    `directory` wins and `base_dir` is ignored).
    `base_dir`: parent directory a freshly minted, uniquely-named staging
    directory is created under when `directory` is not given; defaults
    to the system temp directory.

    Returns {"status": "NONE"} if `files` is empty. Otherwise
    {"status": "OK", "directory": <path>, "files_written": [...]} on
    success, or {"status": "ERROR", "error": "..."} if the staging
    directory can't be created/cleared, or if writing a file doesn't
    verify.

    VERIFICATION: each file is immediately re-measured on disk after
    writing and compared by byte length against what was supposed to be
    written -- load_directory_context has no way to know what SHOULD be
    on disk, only to report whatever it actually finds there, so this is
    the one place that can catch a silently incomplete write (e.g. a
    full disk) before an agent ever gets a chance to misread "nothing
    usable in this directory" as "the user's attachment had no content"
    rather than "staging it failed."

    SECURITY: `name` is caller-controlled (ultimately the end user's own
    browser-reported filename) -- reduced to its basename and rejected if
    that basename is empty, ".", "..", or still contains a path separator
    afterward, so a crafted name (e.g. "../../etc/cron.d/x") can never
    write outside the staging directory.
    """
    if not files:
        return {"status": "NONE"}

    if directory:
        staging_dir = directory
        try:
            os.makedirs(staging_dir, exist_ok=True)
            for existing_name in os.listdir(staging_dir):
                existing_path = os.path.join(staging_dir, existing_name)
                if os.path.isfile(existing_path):
                    os.remove(existing_path)
        except OSError as e:
            return {"status": "ERROR", "error": f"could not prepare staging directory {staging_dir}: {e}"}
    else:
        parent = base_dir or tempfile.gettempdir()
        try:
            staging_dir = tempfile.mkdtemp(prefix="process_architect_attachments_", dir=parent)
        except OSError as e:
            return {"status": "ERROR", "error": f"could not create a staging directory under {parent}: {e}"}

    files_written = []
    for f in files:
        name = f.get("name") or ""
        data = f.get("data") or b""
        safe_name = os.path.basename(name)
        if not safe_name or safe_name in (".", "..") or os.sep in safe_name:
            return {"status": "ERROR", "error": f"unsafe attachment filename: {name!r}"}

        dest_path = os.path.join(staging_dir, safe_name)
        try:
            with open(dest_path, "wb") as out:
                out.write(data)
            actual_size = os.path.getsize(dest_path)
        except OSError as e:
            return {"status": "ERROR", "error": f"failed to stage '{safe_name}': {e}"}

        if actual_size != len(data):
            return {
                "status": "ERROR",
                "error": (
                    f"'{safe_name}' staged incorrectly: wrote {len(data)} bytes, "
                    f"found {actual_size} on disk"
                ),
            }
        files_written.append(safe_name)

    return {"status": "OK", "directory": staging_dir, "files_written": files_written}
