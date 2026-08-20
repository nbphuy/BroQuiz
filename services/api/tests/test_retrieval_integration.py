"""Opt-in real PostgreSQL + Ollama semantic-retrieval smoke test.

Run with: BROQUIZ_RUN_INTEGRATION=1 uv run pytest tests/test_retrieval_integration.py
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk


pytestmark = pytest.mark.skipif(
    os.getenv("BROQUIZ_RUN_INTEGRATION") != "1",
    reason="requires local PostgreSQL and Ollama; set BROQUIZ_RUN_INTEGRATION=1",
)


def build_three_page_pdf() -> bytes:
    pages = [
        "Human-computer interaction studies the design and use of interactive computer systems and interfaces.",
        "Database systems organize persistent structured data using tables, records, and queries.",
        "Computer networks allow machines to communicate using protocols and connected systems.",
    ]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{index} 0 R" for index in range(3, 6))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count 3 >>".encode())
    for page_number, page_text in enumerate(pages):
        content_object = 6 + page_number
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 9 0 R >> >> "
                f"/Contents {content_object} 0 R >>"
            ).encode()
        )
    for page_text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({page_text}) Tj ET".encode()
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    pdf.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(pdf)


def test_real_semantic_retrieval_pipeline() -> None:
    document_id = None
    try:
        with TestClient(app) as client:
            upload = client.post(
                "/documents",
                files={"file": ("semantic-topics.pdf", build_three_page_pdf(), "application/pdf")},
            )
            assert upload.status_code == 201, upload.text
            document_id = upload.json()["id"]
            document_response = client.get(f"/documents/{document_id}")
            assert document_response.status_code == 200, document_response.text
            document_payload = document_response.json()
            assert document_payload["id"] == document_id
            assert document_payload["filename"] == "semantic-topics.pdf"
            chunk_response = client.post(f"/documents/{document_id}/chunks")
            assert chunk_response.status_code == 200
            embedding_response = client.post(f"/documents/{document_id}/embeddings")
            assert embedding_response.status_code == 200
            embedding_payload = embedding_response.json()
            with SessionLocal() as db:
                document = db.get(Document, document_id)
                assert document is not None
                before_status = document.status
                before_updated_at = document.updated_at
                before_chunks = list(
                    db.execute(
                        select(
                            DocumentChunk.id,
                            DocumentChunk.content,
                            DocumentChunk.page_number,
                            DocumentChunk.chunk_index,
                            DocumentChunk.embedding,
                        )
                        .where(DocumentChunk.document_id == document.id)
                        .order_by(DocumentChunk.chunk_index)
                    )
                )
                assert document.status == "embedded"
                assert len(before_chunks) == chunk_response.json()["chunk_count"]
                assert len(before_chunks) == embedding_payload["embedded_count"]
                assert embedding_payload["dimensions"] == settings.embedding_dimensions
                assert all(row.embedding is not None for row in before_chunks)
                assert all(len(row.embedding) == settings.embedding_dimensions for row in before_chunks)

            hci = client.post(
                f"/documents/{document_id}/search",
                json={"query": "How do people interact with computer interfaces?", "top_k": 3},
            )
            database = client.post(
                f"/documents/{document_id}/search",
                json={"query": "How is persistent structured data stored?", "top_k": 3},
            )
            repeat_hci = client.post(
                f"/documents/{document_id}/search",
                json={"query": "How do people interact with computer interfaces?", "top_k": 3},
            )
            assert hci.status_code == database.status_code == repeat_hci.status_code == 200
            assert hci.json()["results"][0]["page_number"] == 1
            assert database.json()["results"][0]["page_number"] == 2
            assert hci.json()["results"] == repeat_hci.json()["results"]

            with SessionLocal() as db:
                document = db.get(Document, document_id)
                assert document is not None
                assert document.status == before_status == "embedded"
                assert document.updated_at == before_updated_at
                assert len(list(db.scalars(select(Document.id).where(Document.id == document.id)))) == 1
                after_chunks = list(
                    db.execute(
                        select(
                            DocumentChunk.id,
                            DocumentChunk.content,
                            DocumentChunk.page_number,
                            DocumentChunk.chunk_index,
                            DocumentChunk.embedding,
                        )
                        .where(DocumentChunk.document_id == document.id)
                        .order_by(DocumentChunk.chunk_index)
                    )
                )
                assert after_chunks == before_chunks
    finally:
        if document_id:
            with SessionLocal() as db:
                document = db.get(Document, document_id)
                if document is not None:
                    db.delete(document)
                    db.commit()
            Path(__file__).resolve().parents[3].joinpath("data", "uploads", f"{document_id}.pdf").unlink(missing_ok=True)
