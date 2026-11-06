from process_toolkit.ingestion.chunking import chunk_text, count_tokens


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
