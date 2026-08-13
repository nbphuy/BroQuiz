import uuid

import pytest

from app.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import DocumentSearchRequest
from app.services.embedding import EmbeddingServiceUnavailable
from app.services.retrieval_service import RetrievalError, retrieve_chunks


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, document, embedded_chunk_id, rows):
        self.document = document
        self.embedded_chunk_id = embedded_chunk_id
        self.rows = rows
        self.executed_statement = None

    def get(self, model, document_id):
        return self.document if self.document and self.document.id == document_id else None

    def scalar(self, statement):
        return self.embedded_chunk_id

    def execute(self, statement):
        self.executed_statement = statement
        return FakeResult(self.rows)


class RecordingProvider:
    def __init__(self, vector=None):
        self.vector = vector if vector is not None else [0.1] * 768
        self.calls = []

    def embed_texts(self, texts):
        self.calls.append(texts)
        return [self.vector]


class OfflineProvider:
    def embed_texts(self, texts):
        raise EmbeddingServiceUnavailable("offline")


def make_chunk(document_id, page, index, content, embedding=True):
    return DocumentChunk(
        id=uuid.uuid4(),
        document_id=document_id,
        content=content,
        page_number=page,
        chunk_index=index,
        embedding=[0.0] * 768 if embedding else None,
    )


def test_search_request_defaults_and_validates_bounds() -> None:
    request = DocumentSearchRequest(query="  interfaces  ")
    assert request.query == "interfaces"
    assert request.top_k == settings.retrieval_top_k

    with pytest.raises(ValueError):
        DocumentSearchRequest(query="   ")
    with pytest.raises(ValueError):
        DocumentSearchRequest(query="query", top_k=0)
    with pytest.raises(ValueError):
        DocumentSearchRequest(query="query", top_k=settings.retrieval_max_top_k + 1)


def test_retrieval_embeds_once_and_returns_ranked_document_scoped_chunks() -> None:
    document = Document(id=uuid.uuid4(), filename="one.pdf", status="embedded")
    first = make_chunk(document.id, 4, 3, "HCI content")
    second = make_chunk(document.id, 8, 9, "Database content")
    provider = RecordingProvider()
    db = FakeSession(document, first.id, [(first, 0.12), (second, 0.47)])

    results = retrieve_chunks(db, document.id, "human interfaces", 2, provider)

    assert provider.calls == [["human interfaces"]]
    assert [(result.chunk_id, result.cosine_distance) for result in results] == [
        (first.id, 0.12),
        (second.id, 0.47),
    ]
    assert [(result.page_number, result.chunk_index) for result in results] == [(4, 3), (8, 9)]
    compiled = str(db.executed_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "document_chunks.document_id" in compiled
    assert "embedding IS NOT NULL" in compiled
    assert "ORDER BY distance ASC, document_chunks.chunk_index ASC" in compiled
    assert "LIMIT 2" in compiled


def test_retrieval_limits_result_count_and_excludes_null_embeddings_in_sql() -> None:
    document = Document(id=uuid.uuid4(), filename="one.pdf", status="embedded")
    included = make_chunk(document.id, 1, 0, "included")
    null_embedding = make_chunk(document.id, 2, 1, "excluded", embedding=False)
    db = FakeSession(document, included.id, [(included, 0.1)])

    results = retrieve_chunks(db, document.id, "included", 1, RecordingProvider())

    assert [result.chunk_id for result in results] == [included.id]
    assert null_embedding.id not in [result.chunk_id for result in results]
    assert len(results) <= 1
    assert "embedding IS NOT NULL" in str(db.executed_statement)


def test_retrieval_rejects_unembedded_document_and_missing_embedded_chunks() -> None:
    document = Document(id=uuid.uuid4(), filename="one.pdf", status="chunked")
    with pytest.raises(RetrievalError, match="not embedded") as error:
        retrieve_chunks(FakeSession(document, None, []), document.id, "query", 1, RecordingProvider())
    assert error.value.status_code == 409

    document.status = "embedded"
    with pytest.raises(RetrievalError, match="no embedded chunks") as error:
        retrieve_chunks(FakeSession(document, None, []), document.id, "query", 1, RecordingProvider())
    assert error.value.status_code == 409


def test_retrieval_validates_query_vector_dimension_and_provider_availability() -> None:
    document = Document(id=uuid.uuid4(), filename="one.pdf", status="embedded")
    chunk = make_chunk(document.id, 1, 0, "content")

    with pytest.raises(RetrievalError) as invalid_dimension:
        retrieve_chunks(
            FakeSession(document, chunk.id, []), document.id, "query", 1, RecordingProvider([0.0] * 767)
        )
    assert invalid_dimension.value.status_code == 500

    with pytest.raises(RetrievalError) as unavailable:
        retrieve_chunks(FakeSession(document, chunk.id, []), document.id, "query", 1, OfflineProvider())
    assert unavailable.value.status_code == 503
