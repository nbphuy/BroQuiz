import uuid

import pytest

from app.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embedding import EmbeddingServiceUnavailable
from app.services.embedding_service import DocumentEmbeddingError, embed_document


class FakeSession:
    def __init__(self, document, chunks):
        self.document = document
        self.chunks = chunks
        self.committed = False
        self.rolled_back = False

    def get(self, model, document_id):
        return self.document

    def scalars(self, statement):
        return iter(self.chunks)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def refresh(self, instance):
        pass


class RecordingProvider:
    def __init__(self):
        self.batches = []

    def embed_texts(self, texts):
        self.batches.append(texts)
        return [[float(index)] * 768 for index in range(len(texts))]


class FailingProvider:
    def embed_texts(self, texts):
        raise EmbeddingServiceUnavailable("offline")


def make_document_and_chunks(count=3, status="chunked"):
    document = Document(id=uuid.uuid4(), filename="test.pdf", status=status)
    chunks = [
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=document.id,
            content=f"chunk {index}",
            page_number=index + 1,
            chunk_index=index,
        )
        for index in range(count)
    ]
    return document, chunks


def test_batching_preserves_input_order_and_assignment(monkeypatch) -> None:
    document, chunks = make_document_and_chunks(3)
    db = FakeSession(document, chunks)
    provider = RecordingProvider()
    monkeypatch.setattr(settings, "embedding_batch_size", 2)

    result = embed_document(db, document.id, provider)

    assert provider.batches == [["chunk 0", "chunk 1"], ["chunk 2"]]
    assert [chunk.embedding[0] for chunk in chunks] == [0.0, 1.0, 0.0]
    assert result.embedded_count == 3
    assert document.status == "embedded"
    assert db.committed


def test_reembedding_updates_existing_chunk_rows() -> None:
    document, chunks = make_document_and_chunks(2, status="embedded")
    original_ids = [chunk.id for chunk in chunks]
    for chunk in chunks:
        chunk.embedding = [9.0] * 768

    embed_document(FakeSession(document, chunks), document.id, RecordingProvider())

    assert [chunk.id for chunk in chunks] == original_ids
    assert len(chunks) == 2
    assert [chunk.embedding[0] for chunk in chunks] == [0.0, 1.0]


def test_embedding_failure_rolls_back_without_embedded_status() -> None:
    document, chunks = make_document_and_chunks(2)
    db = FakeSession(document, chunks)

    with pytest.raises(DocumentEmbeddingError) as error:
        embed_document(db, document.id, FailingProvider())

    assert error.value.status_code == 503
    assert db.rolled_back
    assert document.status == "chunked"
    assert all(chunk.embedding is None for chunk in chunks)
