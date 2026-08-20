import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.document import Document


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


def test_get_document_is_in_openapi_with_document_response_schema(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/documents/{document_id}"]["get"]

