import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.database import get_db
from app.main import app
from app.models.document import Document
from app.services.chunking_service import ChunkingResult, DocumentChunkingError


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


def test_document_endpoints_are_in_openapi_with_typed_response_schemas(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    document_operation = paths["/documents/{document_id}"]["get"]
    chunking_operation = paths["/documents/{document_id}/chunks"]["post"]

    assert document_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/DocumentResponse")
    assert chunking_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/DocumentChunkingResponse")
