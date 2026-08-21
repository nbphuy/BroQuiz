import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.database import get_db
from app.main import app
from app.models.document import Document
from app.schemas.quiz import (
    GeneratedQuestion,
    GeneratedSource,
    QuizGenerationResponse,
)
from app.services.chunking_service import ChunkingResult, DocumentChunkingError
from app.services.embedding_service import DocumentEmbeddingError, EmbeddingResult
from app.services.quiz_service import QuizGenerationError
from app.services.retrieval_service import RetrievedChunk, RetrievalError


@pytest.fixture
def stored_document() -> Document:
    return Document(
        id=uuid.uuid4(),
        filename="course-notes.pdf",
        content_type="application/pdf",
        file_size=1234,
        status="processed",
        page_count=2,
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        updated_at=datetime(2026, 8, 20, tzinfo=UTC),
    )


@pytest.fixture
def client(stored_document: Document):
    class DocumentSession:
        def get(self, model: type[Document], document_id: uuid.UUID) -> Document | None:
            assert model is Document
            return stored_document if document_id == stored_document.id else None

    def override_get_db():
        yield DocumentSession()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_document_returns_stored_metadata(
    client: TestClient, stored_document: Document
) -> None:
    response = client.get(f"/documents/{stored_document.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(stored_document.id)
    assert payload["filename"] == stored_document.filename


def test_get_document_returns_404_for_nonexistent_uuid(client: TestClient) -> None:
    response = client.get(f"/documents/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_create_document_chunks_returns_the_persisted_chunking_summary(
    client: TestClient, stored_document: Document, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored_document.status = "chunked"
    monkeypatch.setattr(
        documents_api,
        "chunk_document",
        lambda db, document_id: ChunkingResult(stored_document, page_count=2, chunk_count=3),
    )

    response = client.post(f"/documents/{stored_document.id}/chunks")

    assert response.status_code == 200
    assert response.json() == {
        "document_id": str(stored_document.id),
        "status": "chunked",
        "page_count": 2,
        "chunk_count": 3,
    }


@pytest.mark.parametrize("status_code, detail", [(404, "Document not found."), (409, "Document is not ready for chunking.")])
def test_create_document_chunks_exposes_safe_lifecycle_errors(
    client: TestClient,
    stored_document: Document,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    detail: str,
) -> None:
    def fail_chunking(db, document_id):  # noqa: ANN001
        raise DocumentChunkingError(status_code, detail)

    monkeypatch.setattr(documents_api, "chunk_document", fail_chunking)

    response = client.post(f"/documents/{stored_document.id}/chunks")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_create_document_embeddings_returns_persisted_summary(
    client: TestClient, stored_document: Document, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored_document.status = "embedded"
    monkeypatch.setattr(
        documents_api,
        "embed_document",
        lambda db, document_id: EmbeddingResult(
            document=stored_document,
            chunk_count=3,
            embedded_count=3,
        ),
    )

    response = client.post(f"/documents/{stored_document.id}/embeddings")

    assert response.status_code == 200
    assert response.json() == {
        "document_id": str(stored_document.id),
        "status": "embedded",
        "chunk_count": 3,
        "embedded_count": 3,
        "model": "embeddinggemma",
        "dimensions": 768,
    }


@pytest.mark.parametrize(
    "status_code, detail",
    [
        (404, "Document not found."),
        (409, "Document is not ready for embedding."),
        (409, "Document has no chunks to embed."),
        (503, "Embedding service unavailable"),
    ],
)
def test_create_document_embeddings_exposes_safe_errors(
    client: TestClient,
    stored_document: Document,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    detail: str,
) -> None:
    def fail_embedding(db, document_id):  # noqa: ANN001
        raise DocumentEmbeddingError(status_code, detail)

    monkeypatch.setattr(documents_api, "embed_document", fail_embedding)

    response = client.post(f"/documents/{stored_document.id}/embeddings")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_search_document_returns_typed_ranked_results(
    client: TestClient, stored_document: Document, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored_document.status = "embedded"
    chunk_id = uuid.uuid4()
    calls = []

    def retrieve(db, document_id, query, top_k):  # noqa: ANN001
        calls.append((document_id, query, top_k))
        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=stored_document.id,
                content="Human-computer interaction content.",
                page_number=2,
                chunk_index=3,
                similarity=0.875,
            )
        ]

    monkeypatch.setattr(documents_api, "retrieve_chunks", retrieve)
    response = client.post(
        f"/documents/{stored_document.id}/search",
        json={"query": "  human interfaces  ", "top_k": 1},
    )

    assert response.status_code == 200
    assert calls == [(stored_document.id, "human interfaces", 1)]
    assert response.json() == {
        "document_id": str(stored_document.id),
        "query": "human interfaces",
        "top_k": 1,
        "result_count": 1,
        "embedding_model": "embeddinggemma",
        "embedding_dimensions": 768,
        "results": [
            {
                "chunk_id": str(chunk_id),
                "document_id": str(stored_document.id),
                "page_number": 2,
                "chunk_index": 3,
                "content": "Human-computer interaction content.",
                "similarity": 0.875,
            }
        ],
    }
    assert "embedding" not in response.json()["results"][0]


@pytest.mark.parametrize(
    "payload",
    [{}, {"query": "   "}, {"query": "valid", "top_k": 0}, {"query": "valid", "top_k": 21}],
)
def test_search_document_rejects_invalid_requests(
    client: TestClient, stored_document: Document, payload: dict
) -> None:
    response = client.post(f"/documents/{stored_document.id}/search", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "status_code, detail",
    [
        (404, "Document not found."),
        (409, "Document is not embedded and cannot be searched."),
        (409, "Document has incomplete embeddings."),
        (503, "Embedding service unavailable."),
        (500, "Unable to search document chunks."),
    ],
)
def test_search_document_exposes_safe_retrieval_errors(
    client: TestClient,
    stored_document: Document,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    detail: str,
) -> None:
    def fail_retrieval(*args):  # noqa: ANN002
        raise RetrievalError(status_code, detail)

    monkeypatch.setattr(documents_api, "retrieve_chunks", fail_retrieval)
    response = client.post(
        f"/documents/{stored_document.id}/search",
        json={"query": "interfaces"},
    )
    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def quiz_generation_response(document_id: uuid.UUID) -> QuizGenerationResponse:
    return QuizGenerationResponse(
        id=uuid.uuid4(),
        document_id=document_id,
        title="HCI Quiz",
        topic="human interfaces",
        status="ready",
        questions=[
            GeneratedQuestion(
                question="What do interfaces support?",
                options=["Interaction", "Fuel", "Roads", "Weather"],
                correct_answer=0,
                explanation="The retrieved source supports interaction.",
                sources=[
                    GeneratedSource(
                        chunk_id=uuid.uuid4(),
                        page_number=2,
                        chunk_index=3,
                    )
                ],
            )
        ],
    )


def test_generate_quiz_passes_typed_controls_and_returns_persisted_quiz(
    client: TestClient,
    stored_document: Document,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = quiz_generation_response(stored_document.id)
    calls = []

    def generate(db, document_id, topic, question_count, top_k):  # noqa: ANN001
        calls.append((document_id, topic, question_count, top_k))
        return expected

    monkeypatch.setattr(documents_api, "generate_quiz", generate)
    response = client.post(
        f"/documents/{stored_document.id}/quiz/generate",
        json={"topic": "  human interfaces  ", "question_count": 1, "top_k": 7},
    )

    assert response.status_code == 200
    assert calls == [(stored_document.id, "human interfaces", 1, 7)]
    assert response.json() == expected.model_dump(mode="json")
    assert "embedding" not in response.text
    assert "prompt" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"topic": "   "},
        {"topic": "valid", "question_count": 0},
        {"topic": "valid", "question_count": 11},
        {"topic": "valid", "top_k": 0},
        {"topic": "valid", "top_k": 21},
    ],
)
def test_generate_quiz_rejects_invalid_requests(
    client: TestClient,
    stored_document: Document,
    payload: dict,
) -> None:
    response = client.post(
        f"/documents/{stored_document.id}/quiz/generate",
        json=payload,
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "status_code,detail",
    [
        (404, "Document not found."),
        (409, "Document is not embedded and cannot be searched."),
        (409, "Document has incomplete embeddings."),
        (503, "Quiz generation service is unavailable."),
        (502, "Quiz generation returned an invalid response."),
        (500, "Unable to persist quiz."),
    ],
)
def test_generate_quiz_exposes_only_safe_service_errors(
    client: TestClient,
    stored_document: Document,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    detail: str,
) -> None:
    def fail_generation(*_):
        raise QuizGenerationError(status_code, detail)

    monkeypatch.setattr(documents_api, "generate_quiz", fail_generation)
    response = client.post(
        f"/documents/{stored_document.id}/quiz/generate",
        json={"topic": "interfaces"},
    )
    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_generate_quiz_hides_unexpected_internal_failures(
    client: TestClient,
    stored_document: Document,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generation(*_):
        raise RuntimeError("private Ollama prompt and PostgreSQL details")

    monkeypatch.setattr(documents_api, "generate_quiz", fail_generation)
    response = client.post(
        f"/documents/{stored_document.id}/quiz/generate",
        json={"topic": "interfaces"},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to generate quiz."}


def test_document_endpoints_are_in_openapi_with_typed_response_schemas(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    document_operation = paths["/documents/{document_id}"]["get"]
    chunking_operation = paths["/documents/{document_id}/chunks"]["post"]
    embedding_operation = paths["/documents/{document_id}/embeddings"]["post"]
    search_operation = paths["/documents/{document_id}/search"]["post"]
    quiz_operation = paths["/documents/{document_id}/quiz/generate"]["post"]

    assert document_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/DocumentResponse")
    assert chunking_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/DocumentChunkingResponse")
    assert embedding_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/DocumentEmbeddingResponse")
    assert search_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/DocumentSearchRequest")
    assert search_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/DocumentSearchResponse")
    assert quiz_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/QuizGenerationRequest")
    assert quiz_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/QuizGenerationResponse")
