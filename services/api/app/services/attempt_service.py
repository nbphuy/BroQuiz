import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.attempt_answer import AttemptAnswer
from app.models.question import Question
from app.models.question_option import QuestionOption
from app.models.question_source import QuestionSource
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.schemas.quiz import (
    AttemptAnswerSubmission,
    AttemptInProgressResponse,
    AttemptOptionResponse,
    AttemptQuestionResponse,
    AttemptReviewAnswerResponse,
    AttemptSourceResponse,
    AttemptSubmittedResponse,
)


class AttemptError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _quiz_options() -> tuple:
    return (
        selectinload(Quiz.questions).selectinload(Question.options),
        selectinload(Quiz.questions).selectinload(Question.sources),
    )


def _load_quiz(db: Session, quiz_id: uuid.UUID) -> Quiz | None:
    return db.scalar(select(Quiz).where(Quiz.id == quiz_id).options(*_quiz_options()))


def _load_attempt(
    db: Session,
    attempt_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> QuizAttempt | None:
    statement = (
        select(QuizAttempt)
        .where(QuizAttempt.id == attempt_id)
        .options(
            selectinload(QuizAttempt.quiz).selectinload(Quiz.questions).selectinload(Question.options),
            selectinload(QuizAttempt.quiz).selectinload(Quiz.questions).selectinload(Question.sources),
            selectinload(QuizAttempt.answers).selectinload(AttemptAnswer.question),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _safe_response(attempt: QuizAttempt) -> AttemptInProgressResponse:
    questions = [
        AttemptQuestionResponse(
            id=question.id,
            question=question.question_text,
            position=question.position,
            options=[
                AttemptOptionResponse(
                    id=option.id,
                    position=option.position,
                    text=option.option_text,
                )
                for option in sorted(question.options, key=lambda item: item.position)
            ],
        )
        for question in sorted(attempt.quiz.questions, key=lambda item: item.position)
    ]
    return AttemptInProgressResponse(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        title=attempt.quiz.title,
        topic=attempt.quiz.topic,
        status=attempt.status,
        total_questions=attempt.total_questions,
        started_at=attempt.started_at,
        questions=questions,
    )


def _submitted_response(attempt: QuizAttempt) -> AttemptSubmittedResponse:
    answer_by_question = {answer.question_id: answer for answer in attempt.answers}
    answers = []
    for question in sorted(attempt.quiz.questions, key=lambda item: item.position):
        answer = answer_by_question[question.id]
        answers.append(AttemptReviewAnswerResponse(
            question_id=question.id, selected_answer=answer.selected_answer, correct_answer=question.correct_answer,
            is_correct=answer.is_correct, explanation=question.explanation,
            sources=[AttemptSourceResponse(chunk_id=source.chunk_id, page_number=source.page_number, chunk_index=source.chunk_index) for source in sorted(question.sources, key=lambda item: (item.page_number, item.chunk_index, str(item.id)))],
        ))
    return AttemptSubmittedResponse(id=attempt.id, quiz_id=attempt.quiz_id, status=attempt.status, score=attempt.score, total_questions=attempt.total_questions, started_at=attempt.started_at, submitted_at=attempt.submitted_at, answers=answers)  # type: ignore[arg-type]


def start_attempt(db: Session, quiz_id: uuid.UUID) -> AttemptInProgressResponse:
    quiz = _load_quiz(db, quiz_id)
    if quiz is None:
        raise AttemptError(404, "Quiz not found.")
    total_questions = len(quiz.questions)
    if total_questions == 0:
        raise AttemptError(409, "Quiz has no questions.")
    attempt = QuizAttempt(quiz=quiz, status="in_progress", total_questions=total_questions)
    try:
        db.add(attempt)
        db.commit()
    except Exception:
        db.rollback()
        raise
    persisted = _load_attempt(db, attempt.id)
    if persisted is None:
        raise RuntimeError("Created attempt disappeared.")
    return _safe_response(persisted)


def get_attempt(db: Session, attempt_id: uuid.UUID) -> AttemptInProgressResponse | AttemptSubmittedResponse | None:
    attempt = _load_attempt(db, attempt_id)
    if attempt is None:
        return None
    return _submitted_response(attempt) if attempt.status == "submitted" else _safe_response(attempt)


def submit_attempt(db: Session, attempt_id: uuid.UUID, submissions: list[AttemptAnswerSubmission]) -> AttemptSubmittedResponse:
    attempt = _load_attempt(db, attempt_id, for_update=True)
    if attempt is None:
        raise AttemptError(404, "Attempt not found.")
    if attempt.status != "in_progress":
        raise AttemptError(409, "Attempt has already been submitted.")
    if attempt.answers:
        raise AttemptError(409, "Attempt already contains submitted answers.")
    question_by_id = {question.id: question for question in attempt.quiz.questions}
    submitted_ids = [submission.question_id for submission in submissions]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise AttemptError(422, "Duplicate question IDs are not allowed.")
    if set(submitted_ids) != set(question_by_id):
        raise AttemptError(422, "Submitted answers must include every quiz question exactly once.")

    try:
        score = 0
        for submission in submissions:
            question = question_by_id[submission.question_id]
            option = next(
                (option for option in question.options if option.id == submission.option_id),
                None,
            )
            if option is None:
                raise AttemptError(422, "Selected option does not belong to its question.")
            is_correct = option.position == question.correct_answer
            score += is_correct
            db.add(
                AttemptAnswer(
                    attempt=attempt,
                    question=question,
                    selected_answer=option.position,
                    is_correct=is_correct,
                )
            )
        attempt.score = score
        attempt.status = "submitted"
        attempt.submitted_at = datetime.now().astimezone()
        db.commit()
    except Exception:
        db.rollback()
        raise

    completed = _load_attempt(db, attempt_id)
    if completed is None:
        raise RuntimeError("Submitted attempt disappeared.")
    return _submitted_response(completed)
