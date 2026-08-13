import uuid

import pytest
from pydantic import ValidationError

from app.config import settings
from app.schemas.quiz import GeneratedQuestion, GeneratedQuiz, GeneratedSource, QuizGenerationRequest
from app.services.llm import LLMServiceUnavailable, LLMStructuredOutputError
from app.services.quiz_service import QuizGenerationError, generate_quiz
import app.services.quiz_service as quiz_service
from app.services.retrieval_service import RetrievedChunk


class RecordingProvider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def generate_structured(self, messages, response_model):
        self.calls.append((messages, response_model))
        if self.error:
            raise self.error
        return self.result


def make_chunk(page=2, content="Interfaces let people interact with computer systems."):
    document_id = uuid.uuid4()
    return RetrievedChunk(uuid.uuid4(), document_id, content, page, 0, 0.1)


def make_quiz(chunk, page=None, chunk_id=None):
    return GeneratedQuiz(
        title="HCI Quiz",
        questions=[
            GeneratedQuestion(
                question="What do interfaces let people do?",
                options=["Interact with systems", "Print only", "Store fuel", "Build roads"],
                correct_answer=0,
                explanation="The source describes interaction with computer systems.",
                sources=[GeneratedSource(chunk_id=chunk_id or chunk.chunk_id, page_number=page or chunk.page_number)],
            )
        ],
    )


def test_quiz_request_defaults_and_validates_bounds() -> None:
    request = QuizGenerationRequest(topic="  human interfaces ")
    assert request.topic == "human interfaces"
    assert request.question_count == settings.quiz_default_question_count
    with pytest.raises(ValidationError):
        QuizGenerationRequest(topic="topic", question_count=0)
    with pytest.raises(ValidationError):
        QuizGenerationRequest(topic="topic", question_count=settings.quiz_max_question_count + 1)


def test_mcq_schema_requires_four_options_and_valid_answer_index() -> None:
    source = GeneratedSource(chunk_id=uuid.uuid4(), page_number=1)
    base = dict(question="Question", correct_answer=0, explanation="Explanation", sources=[source])
    with pytest.raises(ValidationError):
        GeneratedQuestion(options=["one", "two", "three"], **base)
    with pytest.raises(ValidationError):
        GeneratedQuestion(options=["one", "two", "three", "four"], correct_answer=4, **{k: v for k, v in base.items() if k != "correct_answer"})


def test_generation_reuses_retrieval_and_places_retrieved_content_in_context(monkeypatch) -> None:
    chunk = make_chunk(content="A usability goal is effectiveness.")
    calls = []

    def retrieve(db, document_id, topic, top_k):
        calls.append((db, document_id, topic, top_k))
        return [chunk]

    provider = RecordingProvider(make_quiz(chunk))
    document_id = uuid.uuid4()
    expected = object()
    monkeypatch.setattr(quiz_service, "_persist_quiz", lambda *_: expected)
    response = generate_quiz(object(), document_id, "usability", 1, provider=provider, retrieve=retrieve)

    assert calls == [(calls[0][0], document_id, "usability", settings.quiz_retrieval_top_k)]
    user_message = provider.calls[0][0][1]["content"]
    assert str(chunk.chunk_id) in user_message
    assert "page=2" in user_message
    assert chunk.content in user_message
    assert response is expected


def test_fabricated_or_wrong_page_sources_are_rejected() -> None:
    chunk = make_chunk()
    fake_provider = RecordingProvider(make_quiz(chunk, chunk_id=uuid.uuid4()))
    wrong_page_provider = RecordingProvider(make_quiz(chunk, page=chunk.page_number + 1))
    retrieve = lambda *_: [chunk]
    with pytest.raises(QuizGenerationError, match="invalid source") as fabricated:
        generate_quiz(object(), uuid.uuid4(), "interfaces", 1, provider=fake_provider, retrieve=retrieve)
    assert fabricated.value.status_code == 502
    with pytest.raises(QuizGenerationError, match="invalid source"):
        generate_quiz(object(), uuid.uuid4(), "interfaces", 1, provider=wrong_page_provider, retrieve=retrieve)


def test_malformed_output_and_unavailable_llm_map_to_safe_errors() -> None:
    chunk = make_chunk()
    retrieve = lambda *_: [chunk]
    with pytest.raises(QuizGenerationError) as malformed:
        generate_quiz(object(), uuid.uuid4(), "interfaces", 1, provider=RecordingProvider(error=LLMStructuredOutputError()), retrieve=retrieve)
    assert malformed.value.status_code == 502
    assert malformed.value.detail == "Quiz generation returned an invalid response."
    with pytest.raises(QuizGenerationError) as unavailable:
        generate_quiz(object(), uuid.uuid4(), "interfaces", 1, provider=RecordingProvider(error=LLMServiceUnavailable()), retrieve=retrieve)
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail == "Quiz generation service is unavailable."


def test_invalid_generation_never_reaches_persistence(monkeypatch) -> None:
    chunk = make_chunk()
    called = False
    def persist(*_):
        nonlocal called
        called = True
    monkeypatch.setattr(quiz_service, "_persist_quiz", persist)
    with pytest.raises(QuizGenerationError):
        generate_quiz(object(), uuid.uuid4(), "interfaces", 1, provider=RecordingProvider(make_quiz(chunk, chunk_id=uuid.uuid4())), retrieve=lambda *_: [chunk])
    assert not called
