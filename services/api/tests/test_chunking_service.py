import uuid

import pytest

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services import chunking_service
from app.services.chunking_service import (
    DocumentChunkingError,
    chunk_document,
    chunk_extracted_pages,
    chunk_page_text,
)
from app.services.pdf_service import ExtractedPage


class FakeSession:
    def __init__(self, document: Document | None, chunks: list[DocumentChunk] | None = None) -> None:
        self.document = document
        self.chunks = chunks or []
        self.commit_count = 0
        self.rolled_back = False

    def get(self, model: type[Document], document_id: uuid.UUID) -> Document | None:
        assert model is Document
        return self.document if self.document and document_id == self.document.id else None

    def scalars(self, statement):  # noqa: ANN001
        return iter(self.chunks)

    def execute(self, statement):  # noqa: ANN001
        self.chunks.clear()

    def add_all(self, chunks: list[DocumentChunk]) -> None:
        self.chunks.extend(chunks)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rolled_back = True

    def refresh(self, instance: Document) -> None:
        pass


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


def test_chunk_document_persists_page_aware_chunks_and_marks_document_chunked(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    document = Document(id=uuid.uuid4(), filename="course.pdf", status="processed", page_count=2)
    db = FakeSession(document)
    monkeypatch.setattr(chunking_service.settings, "upload_directory", tmp_path)
    (tmp_path / f"{document.id}.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(
        chunking_service,
        "extract_pdf_pages",
        lambda path: [ExtractedPage(1, "First page."), ExtractedPage(2, "Second page.")],
    )

    result = chunk_document(db, document.id)

    assert result.chunk_count == 2
    assert result.page_count == 2
    assert document.status == "chunked"
    assert db.commit_count == 1
    assert [(chunk.document_id, chunk.page_number, chunk.chunk_index) for chunk in db.chunks] == [
        (document.id, 1, 0),
        (document.id, 2, 1),
    ]


def test_repeated_chunking_returns_existing_chunks_without_recreating_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    document = Document(id=uuid.uuid4(), filename="course.pdf", status="chunked", page_count=1)
    existing_chunks = [
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=document.id,
            content="Existing chunk.",
            page_number=1,
            chunk_index=0,
        )
    ]
    db = FakeSession(document, existing_chunks)
    monkeypatch.setattr(chunking_service.settings, "upload_directory", tmp_path)
    monkeypatch.setattr(
        chunking_service,
        "extract_pdf_pages",
        lambda path: pytest.fail("Chunked documents must not be extracted again."),
    )

    result = chunk_document(db, document.id)

    assert result.chunk_count == 1
    assert result.page_count == 1
    assert db.chunks == existing_chunks
    assert db.commit_count == 0


@pytest.mark.parametrize("status", ["uploaded", "processing", "failed", "embedded"])
def test_chunk_document_rejects_documents_outside_the_chunking_lifecycle(status: str) -> None:
    document = Document(id=uuid.uuid4(), filename="course.pdf", status=status)

    with pytest.raises(DocumentChunkingError, match="not ready") as error:
        chunk_document(FakeSession(document), document.id)

    assert error.value.status_code == 409


def test_chunk_document_returns_not_found_for_a_missing_document() -> None:
    with pytest.raises(DocumentChunkingError, match="not found") as error:
        chunk_document(FakeSession(None), uuid.uuid4())

    assert error.value.status_code == 404

class RollbackAwareSession(FakeSession):
    def __init__(self, document: Document) -> None:
        super().__init__(document)
        self.persisted_status = document.status

    def commit(self) -> None:
        raise RuntimeError("database write failed")

    def rollback(self) -> None:
        super().rollback()
        if self.document is not None:
            self.document.status = self.persisted_status


def test_chunk_persistence_failure_rolls_back_the_status_transition(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    document = Document(id=uuid.uuid4(), filename="course.pdf", status="processed", page_count=1)
    db = RollbackAwareSession(document)
    monkeypatch.setattr(chunking_service.settings, "upload_directory", tmp_path)
    (tmp_path / f"{document.id}.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(chunking_service, "extract_pdf_pages", lambda path: [ExtractedPage(1, "Page text.")])

    with pytest.raises(RuntimeError, match="database write failed"):
        chunk_document(db, document.id)

    assert db.rolled_back
    assert document.status == "processed"
