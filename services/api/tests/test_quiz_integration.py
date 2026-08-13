"""Opt-in real PostgreSQL + Ollama quiz-generation smoke test.

Run with: BROQUIZ_RUN_INTEGRATION=1 uv run pytest tests/test_quiz_integration.py
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from app.database import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.question import Question
from app.models.question_option import QuestionOption
from app.models.question_source import QuestionSource
from app.models.quiz import Quiz


pytestmark = pytest.mark.skipif(
    os.getenv("BROQUIZ_RUN_INTEGRATION") != "1",
    reason="requires local PostgreSQL and Ollama; set BROQUIZ_RUN_INTEGRATION=1",
)


def build_quiz_pdf() -> bytes:
    text = (
        "Human-computer interaction, or HCI, studies the design and use of interactive computer "
        "systems. Usability evaluates how effectively, efficiently, and satisfactorily users achieve "
        "their goals. A user interface includes controls and displays through which a person interacts "
        "with a system."
    )
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    pdf.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(pdf)


def test_real_grounded_quiz_generation_pipeline() -> None:
    document_id = None
    try:
        with TestClient(app) as client:
            upload = client.post("/documents", files={"file": ("hci.pdf", build_quiz_pdf(), "application/pdf")})
            assert upload.status_code == 201, upload.text
            document_id = upload.json()["id"]
            assert client.post(f"/documents/{document_id}/chunks").status_code == 200
            assert client.post(f"/documents/{document_id}/embeddings").status_code == 200
            with SessionLocal() as db:
                chunks = list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document_id)))
                valid_sources = {(str(chunk.id), chunk.page_number) for chunk in chunks}

            response = client.post(
                f"/documents/{document_id}/quiz/generate",
                json={"topic": "human-computer interaction and usability", "question_count": 3},
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            quiz_id = payload["id"]
            assert len(payload["questions"]) == 3
            for question in payload["questions"]:
                assert len(question["options"]) == 4
                assert 0 <= question["correct_answer"] <= 3
                assert question["explanation"].strip()
                assert question["sources"]
                assert all((source["chunk_id"], source["page_number"]) in valid_sources for source in question["sources"])

            get_response = client.get(f"/quizzes/{quiz_id}")
            assert get_response.status_code == 200
            assert get_response.json() == payload

            with SessionLocal() as db:
                assert {"quizzes", "questions", "question_options", "question_sources"} <= set(inspect(db.bind).get_table_names())
                assert db.get(Document, document_id) is not None
                assert db.get(Quiz, quiz_id) is not None
                assert len(list(db.scalars(select(Question).where(Question.quiz_id == quiz_id)))) == 3
                assert db.scalar(select(func.count(QuestionOption.id)).join(Question).where(Question.quiz_id == quiz_id)) == 12
                assert db.scalar(select(func.count(QuestionSource.id)).join(Question).where(Question.quiz_id == quiz_id)) >= 3
                document = db.get(Document, document_id)
                assert document is not None
                document.status = "processed"
                db.commit()

            assert client.post(f"/documents/{document_id}/chunks").status_code == 200
            with SessionLocal() as db:
                assert db.get(Quiz, quiz_id) is not None
                sources = list(db.scalars(select(QuestionSource).join(Question).where(Question.quiz_id == quiz_id)))
                assert sources
                assert all(source.chunk_id is None for source in sources)
                assert all(source.page_number > 0 and source.chunk_index >= 0 for source in sources)
    finally:
        if document_id:
            with SessionLocal() as db:
                document = db.get(Document, document_id)
                if document is not None:
                    db.delete(document)
                    db.commit()
            Path(__file__).resolve().parents[3].joinpath("data", "uploads", f"{document_id}.pdf").unlink(missing_ok=True)
