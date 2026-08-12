from app.services.chunking_service import chunk_extracted_pages, chunk_page_text
from app.services.pdf_service import ExtractedPage


def test_empty_and_whitespace_pages_produce_no_chunks() -> None:
    chunks = chunk_extracted_pages([ExtractedPage(1, " \r\n\r\n ")], chunk_size=20, overlap=5)
    assert chunks == []


def test_short_page_produces_one_normalized_chunk() -> None:
    chunks = chunk_extracted_pages([ExtractedPage(1, "  Hello\r\n\r\n\r\nworld.  ")], chunk_size=50, overlap=5)
    assert [(chunk.content, chunk.page_number, chunk.chunk_index) for chunk in chunks] == [
        ("Hello\n\nworld.", 1, 0)
    ]


def test_long_page_respects_size_and_has_overlap() -> None:
    text = "word " * 100
    chunks = chunk_page_text(text, 1, chunk_size=80, overlap=20)
    assert len(chunks) > 1
    assert all(len(content) <= 80 for content, _ in chunks)
    assert chunks[0][0][-15:] in chunks[1][0]


def test_pages_stay_separate_and_indices_are_global_and_deterministic() -> None:
    pages = [ExtractedPage(1, "alpha " * 25), ExtractedPage(2, "beta " * 25), ExtractedPage(3, "")]
    first = chunk_extracted_pages(pages, chunk_size=50, overlap=10)
    second = chunk_extracted_pages(pages, chunk_size=50, overlap=10)
    assert first == second
    assert {chunk.page_number for chunk in first} == {1, 2}
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
    assert all(chunk.content.strip() for chunk in first)


def test_long_text_without_whitespace_makes_forward_progress() -> None:
    chunks = chunk_page_text("x" * 201, 1, chunk_size=50, overlap=10)
    assert len(chunks) > 1
    assert all(0 < len(content) <= 50 for content, _ in chunks)
