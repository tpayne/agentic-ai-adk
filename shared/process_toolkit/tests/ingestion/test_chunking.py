from process_toolkit.ingestion.chunking import chunk_and_wrap, chunk_text, count_tokens, wrap_untrusted


def test_count_tokens_of_empty_string_is_zero():
    assert count_tokens("") == 0
    assert count_tokens(None) == 0


def test_count_tokens_is_positive_for_real_text():
    assert count_tokens("Vendor onboarding requires a 3-day SLA.") > 0


def test_chunk_text_of_empty_string_returns_empty_list():
    assert chunk_text("", max_tokens=100) == []
    assert chunk_text("   \n\n  ", max_tokens=100) == []


def test_text_within_budget_is_returned_as_a_single_unsplit_chunk():
    text = "Vendor onboarding requires KYC checks and a 3-day SLA."
    chunks = chunk_text(text, max_tokens=1000)
    assert chunks == [text]


def test_text_over_budget_is_split_into_multiple_chunks():
    # Many distinct paragraphs, well over a small token budget.
    paragraphs = [f"Requirement FR-{i:03d}: the system shall do thing number {i}." for i in range(200)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_tokens=200, overlap_tokens=20)

    assert len(chunks) > 1
    for chunk in chunks:
        assert count_tokens(chunk) <= 200 + 20  # budget + a little slack for the carried-forward overlap
    # Every paragraph must survive somewhere in the output -- chunking must
    # never silently drop content, only split it.
    for para in paragraphs:
        assert any(para in chunk for chunk in chunks), f"lost paragraph: {para}"


def test_consecutive_chunks_share_an_overlap_so_no_boundary_requirement_is_missed():
    paragraphs = [f"Requirement FR-{i:03d}: the system shall do thing number {i}." for i in range(100)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_tokens=200, overlap_tokens=30)

    assert len(chunks) > 2
    # The tail of each chunk (other than the last) should reappear at the
    # start of the next one -- that's the whole point of the overlap.
    for i in range(len(chunks) - 1):
        last_paragraph_of_chunk = chunks[i].split("\n\n")[-1]
        assert last_paragraph_of_chunk in chunks[i + 1]


def test_a_single_paragraph_larger_than_the_budget_is_hard_split_on_word_boundaries():
    huge_paragraph = " ".join(f"word{i}" for i in range(2000))  # one paragraph, no blank lines
    chunks = chunk_text(huge_paragraph, max_tokens=100, overlap_tokens=0)

    assert len(chunks) > 1
    for chunk in chunks:
        assert count_tokens(chunk) <= 100
        # Never cut a word in half.
        for word in chunk.split():
            assert word.startswith("word")
    # No content lost across the hard split.
    rejoined = " ".join(chunks)
    for i in range(2000):
        assert f"word{i}" in rejoined


def test_chunking_is_deterministic_for_the_same_input():
    text = "\n\n".join(f"Paragraph {i} with some filler content to take up space." for i in range(50))
    first = chunk_text(text, max_tokens=150, overlap_tokens=10)
    second = chunk_text(text, max_tokens=150, overlap_tokens=10)
    assert first == second


def test_wrap_untrusted_adds_the_boundary_and_the_instruction_reminder():
    wrapped = wrap_untrusted("some source content")
    assert "<untrusted_source_document" in wrapped
    assert "</untrusted_source_document>" in wrapped
    assert "DATA to analyze" in wrapped
    assert "some source content" in wrapped


def test_wrap_untrusted_tags_chunk_position_when_given():
    wrapped = wrap_untrusted("text", chunk_index=2, chunk_total=5)
    assert 'chunk="3" chunk_total="5"' in wrapped


def test_chunk_and_wrap_small_text_is_a_single_wrapped_chunk():
    result = chunk_and_wrap("short text", max_tokens=1000)
    assert result["chunk_count"] == 1
    assert len(result["chunks"]) == 1
    assert "short text" in result["chunks"][0]
    assert "<untrusted_source_document" in result["chunks"][0]
    assert "chunks_truncated" not in result


def test_chunk_and_wrap_large_text_produces_multiple_wrapped_chunks():
    paragraphs = [f"Item {i}: some content here." for i in range(200)]
    text = "\n\n".join(paragraphs)
    result = chunk_and_wrap(text, max_tokens=100, overlap_tokens=10, max_chunks=50)
    assert result["chunk_count"] > 1
    for i, chunk in enumerate(result["chunks"]):
        assert f'chunk="{i + 1}" chunk_total="{result["chunk_count"]}"' in chunk


def test_chunk_and_wrap_caps_at_max_chunks_with_an_explicit_signal():
    paragraphs = [f"Item {i}: filler." for i in range(500)]
    text = "\n\n".join(paragraphs)
    result = chunk_and_wrap(text, max_tokens=50, overlap_tokens=5, max_chunks=3)
    assert result["chunk_count"] == 3
    assert result["chunks_truncated"] is True
    assert result["total_chunks_before_cap"] > 3
