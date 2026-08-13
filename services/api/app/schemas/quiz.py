import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.config import settings


class GeneratedSource(BaseModel):
    chunk_id: uuid.UUID | None
    page_number: Annotated[int, Field(gt=0)]
    chunk_index: Annotated[int, Field(ge=0)] | None = None


class GeneratedQuestion(BaseModel):
    question: Annotated[str, Field(min_length=1)]
    options: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=4, max_length=4)]
    correct_answer: Annotated[int, Field(ge=0, le=3)]
    explanation: Annotated[str, Field(min_length=1)]
    sources: Annotated[list[GeneratedSource], Field(min_length=1)]

    @field_validator("question", "explanation")
    @classmethod
    def validate_nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be empty")
        return value

    @field_validator("options")
    @classmethod
    def strip_options(cls, value: list[str]) -> list[str]:
        cleaned = [option.strip() for option in value]
        if any(not option for option in cleaned):
            raise ValueError("options must not be empty")
        return cleaned


class GeneratedQuiz(BaseModel):
    title: Annotated[str, Field(min_length=1)]
    questions: Annotated[list[GeneratedQuestion], Field(min_length=1)]

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value


class QuizGenerationRequest(BaseModel):
    topic: Annotated[str, Field(min_length=1)]
    question_count: int = Field(default_factory=lambda: settings.quiz_default_question_count)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("topic must not be empty")
        return value

    @field_validator("question_count")
    @classmethod
    def validate_question_count(cls, value: int) -> int:
        if not 1 <= value <= settings.quiz_max_question_count:
            raise ValueError(f"question_count must be between 1 and {settings.quiz_max_question_count}")
        return value


class QuizResponse(GeneratedQuiz):
    id: uuid.UUID
    document_id: uuid.UUID
    topic: str
    status: str


class QuizGenerationResponse(QuizResponse):
    pass


class AttemptOptionResponse(BaseModel):
    position: int
    text: str


class AttemptQuestionResponse(BaseModel):
    id: uuid.UUID
    question: str
    position: int
    options: list[AttemptOptionResponse]


class AttemptAnswerSubmission(BaseModel):
    question_id: uuid.UUID
    selected_answer: Annotated[int, Field(ge=0, le=3)]


class AttemptSubmissionRequest(BaseModel):
    answers: list[AttemptAnswerSubmission]


class AttemptSourceResponse(BaseModel):
    chunk_id: uuid.UUID | None
    page_number: int
    chunk_index: int


class AttemptReviewAnswerResponse(BaseModel):
    question_id: uuid.UUID
    selected_answer: int
    correct_answer: int
    is_correct: bool
    explanation: str
    sources: list[AttemptSourceResponse]


class AttemptInProgressResponse(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    status: str
    started_at: datetime
    questions: list[AttemptQuestionResponse]


class AttemptSubmittedResponse(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    status: str
    score: int
    total_questions: int
    started_at: datetime
    submitted_at: datetime
    answers: list[AttemptReviewAnswerResponse]
