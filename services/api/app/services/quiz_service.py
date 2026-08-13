import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models.question import Question
from app.models.question_option import QuestionOption
from app.models.question_source import QuestionSource
from app.models.quiz import Quiz
from app.schemas.quiz import GeneratedQuiz, GeneratedQuestion, GeneratedSource, QuizGenerationResponse, QuizResponse
from app.services.llm import LLMProvider, LLMServiceUnavailable, LLMStructuredOutputError, OllamaLLMProvider
from app.services.retrieval_service import RetrievedChunk, RetrievalError, retrieve_chunks


class QuizGenerationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider.lower() == "ollama":
        return OllamaLLMProvider()
    raise QuizGenerationError(500, "LLM provider is not configured.")


def _build_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[SOURCE chunk_id={chunk.chunk_id} page={chunk.page_number}]\n{chunk.content}"
        for chunk in chunks
    )


def _build_messages(topic: str, question_count: int, context: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You create grounded multiple-choice quizzes. Use only the supplied source context, "
                "not outside knowledge. Every question must be answerable from that context. "
                "Each question needs exactly four plausible options, one correct option index from 0 to 3, "
                "a concise explanation, and one or more citations using only the supplied chunk IDs and pages. "
                "Do not include reasoning or any text outside the requested structured response."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Create exactly {question_count} questions about: {topic}\n\n"
                f"SOURCE CONTEXT:\n{context}"
            ),
        },
    ]


def _validate_sources(quiz: GeneratedQuiz, chunks: list[RetrievedChunk]) -> None:
    allowed_sources = {chunk.chunk_id: chunk for chunk in chunks}
    for question in quiz.questions:
        for source in question.sources:
            if (chunk := allowed_sources.get(source.chunk_id)) is None or chunk.page_number != source.page_number:
                raise QuizGenerationError(502, "Generated quiz contained invalid source references.")


def _response_from_quiz(quiz: Quiz) -> QuizResponse:
    questions = [
        GeneratedQuestion(
            question=question.question_text,
            options=[option.option_text for option in sorted(question.options, key=lambda item: item.position)],
            correct_answer=question.correct_answer,
            explanation=question.explanation,
            sources=[GeneratedSource(chunk_id=source.chunk_id, page_number=source.page_number, chunk_index=source.chunk_index) for source in question.sources],
        )
        for question in sorted(quiz.questions, key=lambda item: item.position)
    ]
    return QuizResponse(id=quiz.id, document_id=quiz.document_id, title=quiz.title, topic=quiz.topic, status=quiz.status, questions=questions)


def get_persisted_quiz(db: Session, quiz_id: uuid.UUID) -> QuizResponse | None:
    statement = select(Quiz).where(Quiz.id == quiz_id).options(
        selectinload(Quiz.questions).selectinload(Question.options),
        selectinload(Quiz.questions).selectinload(Question.sources),
    )
    quiz = db.scalar(statement)
    return _response_from_quiz(quiz) if quiz is not None else None


def _persist_quiz(db: Session, document_id: uuid.UUID, topic: str, generated: GeneratedQuiz, chunks: list[RetrievedChunk]) -> QuizResponse:
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    try:
        quiz = Quiz(document_id=document_id, title=generated.title, topic=topic, status="ready", generator_provider=settings.llm_provider, generator_model=settings.ollama_llm_model)
        db.add(quiz)
        for question_position, generated_question in enumerate(generated.questions):
            question = Question(quiz=quiz, question_text=generated_question.question, correct_answer=generated_question.correct_answer, explanation=generated_question.explanation, position=question_position)
            question.options = [QuestionOption(option_text=text, position=position) for position, text in enumerate(generated_question.options)]
            question.sources = [QuestionSource(chunk_id=source.chunk_id, page_number=source.page_number, chunk_index=chunk_by_id[source.chunk_id].chunk_index) for source in generated_question.sources]
            db.add(question)
        db.flush()
        db.commit()
        return get_persisted_quiz(db, quiz.id)  # type: ignore[arg-type]
    except Exception as exc:
        db.rollback()
        raise QuizGenerationError(500, "Unable to persist quiz.") from exc


def generate_quiz(
    db: Session,
    document_id: uuid.UUID,
    topic: str,
    question_count: int,
    *,
    provider: LLMProvider | None = None,
    retrieve: Callable[[Session, uuid.UUID, str, int], list[RetrievedChunk]] = retrieve_chunks,
) -> QuizGenerationResponse:
    try:
        chunks = retrieve(db, document_id, topic, settings.quiz_retrieval_top_k)
    except RetrievalError as exc:
        raise QuizGenerationError(exc.status_code, exc.detail) from exc
    if not chunks:
        raise QuizGenerationError(409, "No relevant document chunks were found.")

    context = _build_context(chunks)
    provider = provider or get_llm_provider()
    try:
        quiz = provider.generate_structured(_build_messages(topic, question_count, context), GeneratedQuiz)
    except LLMServiceUnavailable as exc:
        raise QuizGenerationError(503, "Quiz generation service is unavailable.") from exc
    except LLMStructuredOutputError as exc:
        raise QuizGenerationError(502, "Quiz generation returned an invalid response.") from exc

    if len(quiz.questions) != question_count:
        raise QuizGenerationError(502, "Quiz generation returned an invalid question count.")
    _validate_sources(quiz, chunks)
    return _persist_quiz(db, document_id, topic, quiz, chunks)
