"""Token-aware text chunking for large source documents.

load_directory_context's own "combined_text" field stays a single,
flat string for backward compatibility (many existing import/analysis
agents key off it directly), but a large directory of RFP/baseline
documents can easily exceed what a single LLM extraction pass should
be asked to reason over in one shot. This module splits that same
content into bounded "chunks" instead, each sized against an actual
token budget rather than a flat character count, so a caller can run
one extraction pass PER CHUNK (map) and merge the partial results
afterward (reduce) instead of silently truncating whatever didn't fit.
"""

from typing import List

_ENCODING_NAME = "cl100k_base"
_encoding = None


def count_tokens(text: str) -> int:
    """Best-effort token count for `text` using tiktoken's cl100k_base
    encoding -- close enough for CHUNK SIZING purposes across providers
    (this is not a billing calculation). Falls back to a conservative
    characters-per-token heuristic (4 chars/token) if tiktoken can't be
    imported or fails for any reason, so chunking degrades gracefully
    rather than crashing the whole directory read.
    """
    if not text:
        return 0
    global _encoding
    try:
        if _encoding is None:
            import tiktoken
            _encoding = tiktoken.get_encoding(_ENCODING_NAME)
        return len(_encoding.encode(text, disallowed_special=()))
    except Exception:
        return max(1, len(text) // 4)


def chunk_text(text: str, max_tokens: int, overlap_tokens: int = 200) -> List[str]:
    """Splits `text` into chunks of at most `max_tokens` tokens each.

    Prefers to break on a blank-line (paragraph) boundary nearest the
    budget rather than mid-sentence. The last `overlap_tokens` worth of
    each chunk is repeated at the start of the next one, so a
    requirement whose own wording straddles a chunk boundary still
    appears whole in at least one chunk rather than being split across
    both and missed by an extraction pass that only sees one side of it.

    Returns `[text]` unchanged if the whole text already fits within
    `max_tokens` (no splitting needed). Returns `[]` for empty or
    whitespace-only text.
    """
    if not text or not text.strip():
        return []
    if count_tokens(text) <= max_tokens:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    current_parts: List[str] = []
    current_tokens = 0

    def flush() -> None:
        if current_parts:
            chunks.append("\n\n".join(current_parts))

    for para in paragraphs:
        para_tokens = count_tokens(para)

        if para_tokens > max_tokens:
            # A single paragraph alone exceeds the budget (one huge
            # unbroken block with no blank lines of its own) -- there's
            # no natural boundary smaller than word-level left to use.
            flush()
            current_parts = []
            current_tokens = 0
            chunks.extend(_hard_split(para, max_tokens))
            continue

        if current_parts and current_tokens + para_tokens > max_tokens:
            flush()
            overlap_text = _tail_by_tokens(chunks[-1], overlap_tokens)
            current_parts = [overlap_text] if overlap_text else []
            current_tokens = count_tokens(overlap_text)

        current_parts.append(para)
        current_tokens += para_tokens

    flush()
    return [c for c in chunks if c.strip()]


def _tail_by_tokens(text: str, max_tokens: int) -> str:
    """Best-effort suffix of `text` with roughly `max_tokens` tokens, used
    to carry a small amount of context forward as overlap into the next
    chunk. Walks back word by word, which is fine for the small overlap
    windows (a couple hundred tokens) this is actually used for."""
    if max_tokens <= 0 or not text:
        return ""
    words = text.split()
    tail_words: List[str] = []
    for word in reversed(words):
        candidate = " ".join([word] + tail_words)
        if count_tokens(candidate) > max_tokens:
            break
        tail_words.insert(0, word)
    return " ".join(tail_words)


def _hard_split(text: str, max_tokens: int) -> List[str]:
    """Splits one oversized paragraph (no blank-line boundaries of its
    own) into pieces of at most max_tokens, breaking on whitespace so
    words are never cut mid-token."""
    words = text.split()
    pieces: List[str] = []
    current: List[str] = []
    for word in words:
        current.append(word)
        if count_tokens(" ".join(current)) > max_tokens:
            current.pop()
            if current:
                pieces.append(" ".join(current))
            current = [word]
    if current:
        pieces.append(" ".join(current))
    return pieces
