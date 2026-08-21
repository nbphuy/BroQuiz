"""Opt-in real PostgreSQL attempt and server-side scoring integration test.

Run with: BROQUIZ_RUN_INTEGRATION=1 uv run pytest tests/test_attempt_integration.py
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.main import app
from app.models.attempt_answer import AttemptAnswer
from app.models.document import Document
from app.models.question import Question
from app.models.question_option import QuestionOption
from app.models.question_source import QuestionSource
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.schemas.quiz import AttemptAnswerSubmission
import app.services.attempt_service as attempt_service


pytestmark = pytest.mark.skipif(
    os.getenv("BROQUIZ_RUN_INTEGRATION") != "1",
    reason="requires local PostgreSQL; set BROQUIZ_RUN_INTEGRATION=1",
)


def create_quiz() -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID], list[list[uuid.UUID]]]:
    with SessionLocal() as db:
        document = Document(filename="attempt-fixture.pdf", content_type="application/pdf", file_size=1, status="processed", page_count=1)
        quiz = Quiz(document=document, title="Attempt fixture", topic="testing", status="ready", generator_provider="test", generator_model="test")
        correct_answers = [1, 3, 0]
        questions = []
        for position, correct_answer in enumerate(correct_answers):
            question = Question(quiz=quiz, question_text=f"Question {position}", correct_answer=correct_answer, explanation=f"Explanation {position}", position=position)
            question.options = [QuestionOption(option_text=f"Q{position} option {option}", position=option) for option in range(4)]
            question.sources = [QuestionSource(page_number=1, chunk_index=position)]
            questions.append(question)
        db.add(quiz)
        db.commit()
        return (
            document.id,
            quiz.id,
            [question.id for question in questions],
            [[option.id for option in question.options] for question in questions],
        )


def test_real_attempt_flow_and_database_constraints() -> None:
    document_id, quiz_id, question_ids, option_ids = create_quiz()
    try:
        with TestClient(app) as client:
            first_start = client.post(f"/quizzes/{quiz_id}/attempts")
            second_start = client.post(f"/quizzes/{quiz_id}/attempts")
            assert first_start.status_code == 201, first_start.text
            assert second_start.status_code == 201, second_start.text
            start_payload = first_start.json()
            assert start_payload["id"] != second_start.json()["id"]
            for forbidden in ("correct_answer", "is_correct", "explanation", "sources"):
                assert forbidden not in first_start.text
            assert [question["position"] for question in start_payload["questions"]] == [0, 1, 2]
            assert all([option["position"] for option in question["options"]] == [0, 1, 2, 3] for question in start_payload["questions"])
            assert all(option["id"] for question in start_payload["questions"] for option in question["options"])

            attempt_id = start_payload["id"]
            in_progress = client.get(f"/attempts/{attempt_id}")
            assert in_progress.status_code == 200
            for forbidden in ("correct_answer", "is_correct", "explanation", "sources"):
                assert forbidden not in in_progress.text

            submitted = client.post(
                f"/attempts/{attempt_id}/submit",
                json={"answers": [
                    {"question_id": str(question_ids[0]), "option_id": str(option_ids[0][1])},
                    {"question_id": str(question_ids[1]), "option_id": str(option_ids[1][2])},
                    {"question_id": str(question_ids[2]), "option_id": str(option_ids[2][0])},
                ]},
            )
            assert submitted.status_code == 200, submitted.text
            payload = submitted.json()
            assert payload["status"] == "submitted"
            assert payload["score"] == 2
            assert payload["total_questions"] == 3
            assert payload["submitted_at"] is not None
            assert [answer["is_correct"] for answer in payload["answers"]] == [True, False, True]
            assert [answer["correct_answer"] for answer in payload["answers"]] == [1, 3, 0]
            assert client.post(f"/attempts/{attempt_id}/submit", json={"answers": []}).status_code == 409
            assert client.get(f"/attempts/{attempt_id}").json() == payload
            assert client.get(f"/attempts/{uuid.uuid4()}").status_code == 404

            with SessionLocal() as db:
                attempt = db.get(QuizAttempt, attempt_id)
                assert attempt is not None and attempt.status == "submitted" and attempt.score == 2 and attempt.submitted_at is not None
                answers = list(db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id)))
                assert len(answers) == 3
                assert [answer.is_correct for answer in sorted(answers, key=lambda answer: str(answer.question_id))].count(True) == 2
                with pytest.raises(IntegrityError):
                    db.add(QuizAttempt(quiz_id=uuid.uuid4(), total_questions=1))
                    db.commit()
                db.rollback()
                with pytest.raises(IntegrityError):
                    db.add(AttemptAnswer(attempt_id=attempt.id, question_id=question_ids[0], selected_answer=1, is_correct=True))
                    db.commit()
                db.rollback()
                with pytest.raises(IntegrityError):
                    db.add(AttemptAnswer(attempt_id=uuid.uuid4(), question_id=question_ids[0], selected_answer=1, is_correct=True))
                    db.commit()
                db.rollback()
                with pytest.raises(IntegrityError):
                    db.add(AttemptAnswer(attempt_id=attempt.id, question_id=question_ids[1], selected_answer=4, is_correct=False))
                    db.commit()
                db.rollback()
                db.delete(attempt)
                db.commit()
                assert db.scalar(select(func.count(AttemptAnswer.id)).where(AttemptAnswer.attempt_id == attempt_id)) == 0

        with SessionLocal() as db:
            quiz = db.get(Quiz, quiz_id)
            assert quiz is not None
            attempt = QuizAttempt(quiz=quiz, total_questions=3)
            db.add(attempt)
            db.commit()
            attempt_id = attempt.id
            db.delete(quiz)
            db.commit()
            assert db.get(QuizAttempt, attempt_id) is None
    finally:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if document is not None:
                db.delete(document)
                db.commit()


def test_submission_write_failure_rolls_back_all_answers(monkeypatch) -> None:
    document_id, quiz_id, question_ids, option_ids = create_quiz()
    try:
        with SessionLocal() as db:
            attempt_id = attempt_service.start_attempt(db, quiz_id).id
            calls = 0
            original_add = db.add

            def fail_on_second_answer(instance, *args, **kwargs):
                nonlocal calls
                if isinstance(instance, AttemptAnswer):
                    calls += 1
                    if calls == 2:
                        raise RuntimeError("forced answer write failure")
                return original_add(instance, *args, **kwargs)

            monkeypatch.setattr(db, "add", fail_on_second_answer)
            with pytest.raises(RuntimeError, match="forced answer write failure"):
                attempt_service.submit_attempt(db, attempt_id, [
                    AttemptAnswerSubmission(question_id=question_id, option_id=option_ids[index][0])
                    for index, question_id in enumerate(question_ids)
                ])
            db.expire_all()
            attempt = db.get(QuizAttempt, attempt_id)
            assert attempt is not None and attempt.status == "in_progress" and attempt.score is None
            assert db.scalar(select(func.count(AttemptAnswer.id)).where(AttemptAnswer.attempt_id == attempt_id)) == 0
    finally:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if document is not None:
                db.delete(document)
                db.commit()
