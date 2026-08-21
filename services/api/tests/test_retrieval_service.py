import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import DocumentSearchRequest
from app.services.embedding import EmbeddingServiceUnavailable
from app.services.retrieval_service import RetrievalError, retrieve_chunks


class FakeResult:
    def __init__(self, rows=None, counts=None):
        self.rows = rows or []
        self.counts = counts

    def all(self):
        return self.rows

    def one(self):
        return self.counts


class FakeSession:
    def __init__(self, document, chunk_count, embedded_count, rows):
        self.document = document
        self.chunk_count = chunk_count
        self.embedded_count = embedded_count
        self.rows = rows
        self.executed_statement = None
        self.write_called = False

    def get(self, model, document_id):
        return self.document if self.document and self.document.id == document_id else None

    def execute(self, statement):
        if "count(" in str(statement):
            return FakeResult(counts=(self.chunk_count, self.embedded_count))
        self.executed_statement = statement
        return FakeResult(self.rows)

    def add(self, instance):
        self.write_called = True

    def commit(self):
        self.write_called = True


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


class ResponseProvider:
    def __init__(self, response):
        self.response = response

    def embed_texts(self, texts):
        return self.response


class BrokenProvider:
    def embed_texts(self, texts):
        raise RuntimeError("provider internals")


class FailingSession(FakeSession):
    def execute(self, statement):
        raise SQLAlchemyError("database internals")


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
    db = FakeSession(document, 2, 2, [(first, 0.12), (second, 0.47)])

    results = retrieve_chunks(db, document.id, "human interfaces", 2, provider)

    assert provider.calls == [["human interfaces"]]
    assert [(result.chunk_id, result.similarity) for result in results] == [
        (first.id, 0.88),
        (second.id, 0.53),
    ]
    assert [(result.page_number, result.chunk_index) for result in results] == [(4, 3), (8, 9)]
    compiled = str(db.executed_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "document_chunks.document_id" in compiled
    assert "embedding IS NOT NULL" in compiled
    assert (
        "ORDER BY cosine_distance ASC, document_chunks.chunk_index ASC, "
        "document_chunks.id ASC"
    ) in compiled
    assert "LIMIT 2" in compiled
    assert not db.write_called
    assert first.embedding == [0.0] * 768


def test_retrieval_limits_result_count_and_excludes_null_embeddings_in_sql() -> None:
    document = Document(id=uuid.uuid4(), filename="one.pdf", status="embedded")
    included = make_chunk(document.id, 1, 0, "included")
    null_embedding = make_chunk(document.id, 2, 1, "excluded", embedding=False)
    db = FakeSession(document, 1, 1, [(included, 0.1)])

    results = retrieve_chunks(db, document.id, "included", 1, RecordingProvider())

    assert [result.chunk_id for result in results] == [included.id]
    assert null_embedding.id not in [result.chunk_id for result in results]
    assert len(results) <= 1
    assert "embedding IS NOT NULL" in str(db.executed_statement)


def test_retrieval_rejects_unembedded_document_and_missing_embedded_chunks() -> None:
    document = Document(id=uuid.uuid4(), filename="one.pdf", status="chunked")
    with pytest.raises(RetrievalError, match="not embedded") as error:
        retrieve_chunks(FakeSession(document, 0, 0, []), document.id, "query", 1, RecordingProvider())
    assert error.value.status_code == 409

    document.status = "embedded"
    with pytest.raises(RetrievalError, match="no embedded chunks") as error:
        retrieve_chunks(FakeSession(document, 0, 0, []), document.id, "query", 1, RecordingProvider())
    assert error.value.status_code == 409

    with pytest.raises(RetrievalError, match="incomplete embeddings") as error:
        retrieve_chunks(FakeSession(document, 2, 1, []), document.id, "query", 1, RecordingProvider())
    assert error.value.status_code == 409


def test_retrieval_validates_query_vector_dimension_and_provider_availability() -> None:
    document = Document(id=uuid.uuid4(), filename="one.pdf", status="embedded")
    chunk = make_chunk(document.id, 1, 0, "content")

    with pytest.raises(RetrievalError) as invalid_dimension:
        retrieve_chunks(
            FakeSession(document, 1, 1, []), document.id, "query", 1, RecordingProvider([0.0] * 767)
        )
    assert invalid_dimension.value.status_code == 500

    with pytest.raises(RetrievalError) as unavailable:
        retrieve_chunks(FakeSession(document, 1, 1, []), document.id, "query", 1, OfflineProvider())
    assert unavailable.value.status_code == 503


def test_retrieval_rejects_missing_document_and_invalid_query_vector_count() -> None:
    document_id = uuid.uuid4()
    with pytest.raises(RetrievalError) as missing:
        retrieve_chunks(FakeSession(None, 0, 0, []), document_id, "query", 1, RecordingProvider())
    assert missing.value.status_code == 404

    document = Document(id=document_id, filename="one.pdf", status="embedded")
    for response in ([], [[0.0] * 768, [0.1] * 768]):
        with pytest.raises(RetrievalError) as malformed:
            retrieve_chunks(
                FakeSession(document, 1, 1, []),
                document.id,
                "query",
                1,
                ResponseProvider(response),
            )
        assert malformed.value.status_code == 500
        assert malformed.value.detail == "Embedding service returned an invalid response."


def test_retrieval_handles_non_numeric_provider_and_database_errors_safely() -> None:
    document = Document(id=uuid.uuid4(), filename="one.pdf", status="embedded")
    malformed_vector = [0.0] * 767 + [float("nan")]
    with pytest.raises(RetrievalError) as malformed:
        retrieve_chunks(
            FakeSession(document, 1, 1, []),
            document.id,
            "query",
            1,
            ResponseProvider([malformed_vector]),
        )
    assert malformed.value.status_code == 500
    assert "nan" not in malformed.value.detail.lower()

    with pytest.raises(RetrievalError) as provider_failure:
        retrieve_chunks(
            FakeSession(document, 1, 1, []),
            document.id,
            "query",
            1,
            BrokenProvider(),
        )
    assert provider_failure.value.status_code == 500
    assert "internals" not in provider_failure.value.detail

    with pytest.raises(RetrievalError) as database_failure:
        retrieve_chunks(
            FailingSession(document, 1, 1, []),
            document.id,
            "query",
            1,
            RecordingProvider(),
        )
    assert database_failure.value.status_code == 500
    assert "internals" not in database_failure.value.detail
