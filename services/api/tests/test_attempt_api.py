import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.attempt_answer import AttemptAnswer
from app.models.base import Base
from app.models.document import Document
from app.models.question import Question
from app.models.question_option import QuestionOption
from app.models.question_source import QuestionSource
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt


class FailingAnswerSession(Session):
    def add(self, instance, *args, **kwargs):
        if self.info.get("fail_answers") and isinstance(instance, AttemptAnswer):
            count = self.info.get("answer_add_count", 0) + 1
            self.info["answer_add_count"] = count
            if count == 2:
                raise RuntimeError("forced answer persistence failure")
        return super().add(instance, *args, **kwargs)


def create_quiz(db: Session, title: str, correct_answers: list[int]) -> Quiz:
    document = Document(
        filename=f"{title}.pdf",
        content_type="application/pdf",
        file_size=1,
        status="processed",
        page_count=1,
    )
    quiz = Quiz(
        document=document,
        title=title,
        topic=f"{title} topic",
        status="ready",
        generator_provider="test",
        generator_model="test",
    )
    for position, correct_answer in enumerate(correct_answers):
        question = Question(
            quiz=quiz,
            question_text=f"{title} question {position + 1}",
            correct_answer=correct_answer,
            explanation=f"{title} secret explanation {position + 1}",
            position=position,
        )
        question.options = [
            QuestionOption(option_text=f"{title} Q{position + 1} option {option + 1}", position=option)
            for option in range(4)
        ]
        question.sources = [QuestionSource(page_number=1, chunk_index=position)]
    db.add(quiz)
    db.commit()
    return quiz


@pytest.fixture
def attempt_api():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, class_=FailingAnswerSession, expire_on_commit=False)
    with TestSession() as db:
        first = create_quiz(db, "Ordered quiz", [1, 3, 0])
        second = create_quiz(db, "Other quiz", [2])
        first_id, second_id = first.id, second.id

    def override_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, TestSession, first_id, second_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def forbidden_player_keys(payload) -> set[str]:
    forbidden = {"correct_answer", "correct_option_id", "is_correct", "explanation", "sources"}
    if isinstance(payload, dict):
        return (set(payload) & forbidden) | set().union(
            *(forbidden_player_keys(value) for value in payload.values()),
        )
    if isinstance(payload, list):
        return set().union(*(forbidden_player_keys(value) for value in payload))
    return set()


def start(client: TestClient, quiz_id: uuid.UUID) -> dict:
    response = client.post(f"/quizzes/{quiz_id}/attempts")
    assert response.status_code == 201, response.text
    return response.json()


def valid_answers(payload: dict) -> list[dict[str, str]]:
    return [
        {"question_id": question["id"], "option_id": question["options"][0]["id"]}
        for question in payload["questions"]
    ]


def test_start_and_read_are_ordered_and_answer_safe(attempt_api) -> None:
    client, _, quiz_id, _ = attempt_api
    first = start(client, quiz_id)
    second = start(client, quiz_id)

    assert first["id"] != second["id"]
    assert first["title"] == "Ordered quiz"
    assert first["topic"] == "Ordered quiz topic"
    assert first["status"] == "in_progress"
    assert first["total_questions"] == 3
    assert [question["position"] for question in first["questions"]] == [0, 1, 2]
    assert all(
        [option["position"] for option in question["options"]] == [0, 1, 2, 3]
        for question in first["questions"]
    )
    assert all(option["id"] for question in first["questions"] for option in question["options"])
    assert forbidden_player_keys(first) == set()

    read = client.get(f"/attempts/{first['id']}")
    assert read.status_code == 200
    assert read.json() == first
    assert forbidden_player_keys(read.json()) == set()
    assert client.get(f"/attempts/{uuid.uuid4()}").status_code == 404
    assert client.post(f"/quizzes/{uuid.uuid4()}/attempts").status_code == 404


def test_submit_is_server_authoritative_and_persists_completion(attempt_api) -> None:
    client, TestSession, quiz_id, _ = attempt_api
    payload = start(client, quiz_id)
    answers = valid_answers(payload)

    rejected = client.post(
        f"/attempts/{payload['id']}/submit",
        json={"answers": [{**answer, "is_correct": True} for answer in answers]},
    )
    assert rejected.status_code == 422

    submitted = client.post(f"/attempts/{payload['id']}/submit", json={"answers": answers})
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["status"] == "submitted"
    assert result["score"] == 1
    assert result["total_questions"] == 3
    assert result["submitted_at"] is not None

    with TestSession() as db:
        attempt = db.get(QuizAttempt, uuid.UUID(payload["id"]))
        assert attempt is not None
        assert attempt.quiz_id == quiz_id
        assert attempt.status == "submitted"
        assert attempt.score == 1
        persisted = list(db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id)))
        assert len(persisted) == 3
        assert all(answer.question_id for answer in persisted)
        assert all(0 <= answer.selected_answer <= 3 for answer in persisted)

    duplicate = client.post(f"/attempts/{payload['id']}/submit", json={"answers": answers})
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Attempt has already been submitted."}


@pytest.mark.parametrize("case", ["missing", "duplicate", "unknown_question", "wrong_option"])
def test_submit_rejects_invalid_question_and_option_sets(attempt_api, case: str) -> None:
    client, TestSession, quiz_id, _ = attempt_api
    payload = start(client, quiz_id)
    answers = valid_answers(payload)
    if case == "missing":
        answers.pop()
    elif case == "duplicate":
        answers[-1]["question_id"] = answers[0]["question_id"]
    elif case == "unknown_question":
        answers[0]["question_id"] = str(uuid.uuid4())
    else:
        answers[0]["option_id"] = payload["questions"][1]["options"][0]["id"]

    response = client.post(f"/attempts/{payload['id']}/submit", json={"answers": answers})
    assert response.status_code == 422
    assert response.json()["detail"] in {
        "Duplicate question IDs are not allowed.",
        "Submitted answers must include every quiz question exactly once.",
        "Selected option does not belong to its question.",
    }
    with TestSession() as db:
        attempt = db.get(QuizAttempt, uuid.UUID(payload["id"]))
        assert attempt is not None and attempt.status == "in_progress" and attempt.score is None
        assert db.scalar(
            select(func.count(AttemptAnswer.id)).where(AttemptAnswer.attempt_id == attempt.id),
        ) == 0


def test_submit_rejects_question_and_option_from_another_quiz(attempt_api) -> None:
    client, _, quiz_id, other_quiz_id = attempt_api
    payload = start(client, quiz_id)
    other = start(client, other_quiz_id)

    wrong_question = valid_answers(payload)
    wrong_question[0]["question_id"] = other["questions"][0]["id"]
    response = client.post(f"/attempts/{payload['id']}/submit", json={"answers": wrong_question})
    assert response.status_code == 422

    wrong_option = valid_answers(payload)
    wrong_option[0]["option_id"] = other["questions"][0]["options"][0]["id"]
    response = client.post(f"/attempts/{payload['id']}/submit", json={"answers": wrong_option})
    assert response.status_code == 422
    assert response.json() == {"detail": "Selected option does not belong to its question."}
    assert client.post(
        f"/attempts/{uuid.uuid4()}/submit",
        json={"answers": valid_answers(payload)},
    ).status_code == 404


def test_submission_failure_rolls_back_attempt_and_answers(attempt_api) -> None:
    client, TestSession, quiz_id, _ = attempt_api
    payload = start(client, quiz_id)

    def failing_db():
        with TestSession() as db:
            db.info["fail_answers"] = True
            yield db

    app.dependency_overrides[get_db] = failing_db
    response = client.post(
        f"/attempts/{payload['id']}/submit",
        json={"answers": valid_answers(payload)},
    )
    assert response.status_code == 500
    assert response.text == "Internal Server Error"

    with TestSession() as db:
        attempt = db.get(QuizAttempt, uuid.UUID(payload["id"]))
        assert attempt is not None and attempt.status == "in_progress"
        assert attempt.score is None and attempt.submitted_at is None
        assert db.scalar(
            select(func.count(AttemptAnswer.id)).where(AttemptAnswer.attempt_id == attempt.id),
        ) == 0
