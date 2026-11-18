"""Per-extension text extractors for load_directory_context.

Ported verbatim from the ADK sample's process_agents/common/utils.py
(_extract_*_file + _DIRECTORY_CONTEXT_EXTRACTORS) -- pure Python, nothing
framework-specific, so the logic carries over unchanged.
"""

import base64
import os
import tempfile

from process_toolkit.ingestion.chunking import chunk_and_wrap, wrap_untrusted


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


def _extract_json_file(path: str) -> str:
    # Unlike .txt/.xml above, this DOES parse (json.loads, not a raw read)
    # -- the two things a .json upload is for here are (a) a previously
    # downloaded process_data.json/design_data.json being re-attached to
    # resume work (see both ports' Process_Import_Agent/Design_Import_Agent
    # instructions, which look for an exact filename + shape match in this
    # extracted text to restore it verbatim rather than re-deriving it),
    # and (b) generic structured source material. Either way, a syntax
    # error is worth surfacing as a clear "failed to read" skip reason
    # (load_directory_context's own except-and-skip handling already does
    # this for any extractor that raises) rather than silently passing
    # malformed text through. Re-serialized with indent=2 so formatting is
    # consistent regardless of how the original file was minified/pretty-
    # printed -- the content, not the original byte-for-byte text, is what
    # matters here.
    import json

    with open(path, "r", encoding="utf-8-sig") as f:
        parsed = json.load(f)
    return json.dumps(parsed, indent=2, ensure_ascii=False)


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


def _extract_pptx_file(path: str) -> str:
    from pptx import Presentation
    prs = Presentation(path)
    slides = []
    for i, slide in enumerate(prs.slides, start=1):
        slide_parts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    slide_parts.append(text)
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        slide_parts.append(" | ".join(cells))
        if slide_parts:
            slides.append(f"[Slide {i}]\n" + "\n".join(slide_parts))
    return "\n\n".join(slides)


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


def _extract_vsdx_file(path: str) -> str:
    # VisioFile.all_shapes (not the deprecated .shapes, which is top-level
    # only) walks every shape on a page, recursively -- confirmed directly
    # against the installed vsdx package. Connector relationships are
    # reconstructed from Page.connects: two Connect entries sharing the same
    # connector_shape_id are the two ends of ONE connector line (confirmed
    # directly: a real connector between shapes "1" and "2" produces
    # Connect(connector_shape_id=5, shape_id=1) and Connect(connector_shape_id=
    # 5, shape_id=2)), so grouping by connector_shape_id recovers which two
    # real shapes (never the connector's own shape) each connector joins.
    # Direction (which end is "begin" vs "end") isn't asserted here -- that
    # would need reading the connector's own geometry cells, not just this
    # list -- so this reports an undirected relationship rather than
    # guessing a direction that might be backwards.
    from vsdx import VisioFile

    sections = []
    with VisioFile(path) as vis:
        for page in vis.pages:
            id_to_text = {}
            shape_lines = []
            for shape in page.all_shapes:
                text = (shape.text or "").strip()
                if text:
                    id_to_text[shape.ID] = text
                    shape_lines.append(text)

            by_connector = {}
            for connect in page.connects:
                by_connector.setdefault(connect.connector_shape_id, []).append(connect.shape_id)

            connection_lines = []
            for shape_ids in by_connector.values():
                labels = list(dict.fromkeys(id_to_text.get(sid, sid) for sid in shape_ids))
                if len(labels) >= 2:
                    connection_lines.append(" -- ".join(labels))

            section = f"[Page: {page.name}]\n" + "\n".join(shape_lines)
            if connection_lines:
                section += "\n\nConnections:\n" + "\n".join(connection_lines)
            sections.append(section)
    return "\n\n".join(sections)


def _extract_image_file(path: str) -> str:
    # OCR extracts visible TEXT only -- same honesty-first limitation as
    # _extract_pdf_file's own no-OCR-on-scanned-pages note above: a
    # box-and-arrow diagram screenshot yields whatever text labels Tesseract
    # can read, roughly in reading order, with NO connection/relationship/
    # layout information recoverable from pixels alone (unlike _extract_vsdx_
    # file above, which has real vector shape+connector data to work with).
    from PIL import Image
    import pytesseract

    with Image.open(path) as image:
        return pytesseract.image_to_string(image)


# Legacy .doc/.ppt (binary, pre-2007 Office) are deliberately absent --
# python-docx/python-pptx only read the modern XML-based .docx/.pptx
# formats. Both are caught in load_directory_context and reported in
# files_skipped with a specific "re-save as .docx"/"re-save as .pptx"
# reason, rather than silently falling through to "unsupported file type".
DIRECTORY_CONTEXT_EXTRACTORS = {
    ".txt": _extract_txt_file,
    ".md": _extract_txt_file,
    ".docx": _extract_docx_file,
    ".pptx": _extract_pptx_file,
    ".pdf": _extract_pdf_file,
    ".eml": _extract_eml_file,
    ".msg": _extract_msg_file,
    ".xls": _extract_excel_file,
    ".xlsx": _extract_excel_file,
    ".xml": _extract_xml_file,
    ".json": _extract_json_file,
    ".vsdx": _extract_vsdx_file,
    ".vsdm": _extract_vsdx_file,
    ".png": _extract_image_file,
    ".jpg": _extract_image_file,
    ".jpeg": _extract_image_file,
    ".gif": _extract_image_file,
    ".webp": _extract_image_file,
    ".bmp": _extract_image_file,
    ".tiff": _extract_image_file,
}

# Extensions load_directory_context ALSO base64-encodes into its own "images"
# return field, on top of their OCR'd text above -- a caller on a framework
# that supports handing a tool's own return value back to the model as real
# vision input (confirmed: Google ADK does, via Part.from_bytes embedded in a
# FunctionTool's own return; confirmed NOT possible via a neuro-san CodedTool's
# own return value, which is force-stringified before any multimodal handling
# could apply) can use this for genuine visual understanding instead of
# OCR-only text. A caller that ignores this field loses nothing -- the OCR'd
# text above is unconditionally still part of combined_text/chunks either way.
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"})

_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
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


def load_directory_context(
    directory: str,
    max_chars: int = 150000,
    chunk_max_tokens: int = 30000,
    chunk_overlap_tokens: int = 200,
    max_chunks: int = 20,
) -> dict:
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
    "files_skipped": [{"file":..., "reason":...}], "combined_text": "...",
    "chunks": [...], "chunk_count": N}.

    "combined_text" is UNCHANGED, existing behavior, kept for every caller
    that already keys off it directly (process/design/cloudarch import and
    analysis agents, literal-restore-by-heading, attachment staging) --
    still a single flat string, still capped at max_chars with a truncation
    note appended if exceeded, now also wrapped in an explicit
    untrusted-data boundary (see _wrap_untrusted) so those existing callers
    get the same prompt-injection framing for free, with no shape change.

    "chunks" is NEW and additive: the SAME content (not the max_chars-
    truncated copy -- the full text), split into token-budgeted pieces of
    at most chunk_max_tokens each (see chunk_text), each independently
    wrapped in its own untrusted-data boundary and tagged with its own
    chunk/chunk_total position. A caller that wants to process a large
    directory via map-reduce -- one extraction pass per chunk, merged
    afterward -- iterates "chunks" instead of truncating "combined_text".
    If the content fits in a single chunk, "chunks" is a one-element list
    (so a chunk-aware caller never needs a special case for "small input").
    Bounded at max_chunks total; if genuinely more chunks than that would
    be needed, the list is capped there and "chunks_truncated": true plus
    "total_chunks_before_cap" are included so a caller can tell the user
    not everything was analyzed, instead of the old behavior of silently
    cutting off mid-character with no visible signal beyond one string.

    "images" is NEW and additive: one {"name", "mime_type", "data_base64"}
    entry per image file found (see IMAGE_EXTENSIONS), independent of
    "files_processed"/"files_skipped"/"combined_text" above -- an image's
    OCR'd text (if any) still flows through "combined_text"/"chunks" exactly
    like every other extractor, but this field exists so a caller on a
    framework that supports handing real image bytes back to the model as
    vision input (see IMAGE_EXTENSIONS's own docstring for which ones do) can
    do that instead of relying on OCR alone. Empty list if no images were
    found; a caller that never looks at this field is unaffected.
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
    images = []

    for name in entries:
        full_path = os.path.join(resolved, name)
        if not os.path.isfile(full_path):
            continue

        ext = os.path.splitext(name)[1].lower()
        extractor = DIRECTORY_CONTEXT_EXTRACTORS.get(ext)
        if extractor is None:
            if ext == ".doc":
                reason = "legacy .doc (unsupported -- re-save as .docx)"
            elif ext == ".ppt":
                reason = "legacy .ppt (unsupported -- re-save as .pptx)"
            else:
                reason = f"unsupported file type '{ext or '(no extension)'}'"
            files_skipped.append({"file": name, "reason": reason})
            continue

        try:
            text = (extractor(full_path) or "").strip()
        except Exception as e:
            files_skipped.append({"file": name, "reason": f"failed to read: {e}"})
            continue

        # An image's raw bytes are captured independently of whether OCR
        # just above found any text -- a diagram that's all boxes/arrows
        # with no text labels at all has EMPTY OCR output but is still
        # genuinely useful to a caller that can hand it to the model as real
        # vision input (see IMAGE_EXTENSIONS's own docstring); gating this on
        # "OCR found non-empty text" would silently drop exactly the images
        # vision passthrough matters most for. This runs AFTER the extractor
        # call above, not before: that call is what actually proves the file
        # is a genuinely decodable image (extractor() opens it via PIL) --
        # capturing raw bytes first, before that validation, would let a
        # corrupt/non-image file with an image-like extension end up in
        # "images" even though it was never a real image at all.
        if ext in IMAGE_EXTENSIONS:
            with open(full_path, "rb") as f:
                raw_bytes = f.read()
            images.append({
                "name": name,
                "mime_type": _IMAGE_MIME_TYPES[ext],
                "data_base64": base64.b64encode(raw_bytes).decode("ascii"),
            })

        if not text:
            files_skipped.append({"file": name, "reason": "no extractable text"})
            continue

        files_processed.append(name)
        sections.append(f"=== {name} ===\n{text}")

    full_text = "\n\n".join(sections)
    truncated = len(full_text) > max_chars
    combined_text = full_text
    if truncated:
        combined_text = full_text[:max_chars] + (
            f"\n\n[... truncated at {max_chars} characters ...]"
        )

    # "chunks" splits the FULL, untruncated text -- large content becomes
    # more chunks rather than being silently cut off the way the legacy
    # "combined_text" field above still is for its own existing callers.
    chunked = chunk_and_wrap(
        full_text, max_tokens=chunk_max_tokens, overlap_tokens=chunk_overlap_tokens, max_chunks=max_chunks,
    )

    result = {
        "status": "OK",
        "directory": resolved,
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "combined_text": wrap_untrusted(combined_text) if combined_text else combined_text,
        "chunks": chunked["chunks"],
        "chunk_count": chunked["chunk_count"],
        "images": images,
    }
    if truncated:
        result["truncated"] = True
    if chunked.get("chunks_truncated"):
        result["chunks_truncated"] = True
        result["total_chunks_before_cap"] = chunked["total_chunks_before_cap"]
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
