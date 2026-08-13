import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.attempt_answer import AttemptAnswer
    from app.models.question_option import QuestionOption
    from app.models.question_source import QuestionSource
    from app.models.quiz import Quiz


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (CheckConstraint("correct_answer >= 0 AND correct_answer <= 3", name="ck_questions_correct_answer_range"), UniqueConstraint("quiz_id", "position", name="uq_questions_quiz_id_position"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")
    options: Mapped[list["QuestionOption"]] = relationship(back_populates="question", cascade="all, delete-orphan", passive_deletes=True)
    sources: Mapped[list["QuestionSource"]] = relationship(back_populates="question", cascade="all, delete-orphan", passive_deletes=True)
    attempt_answers: Mapped[list["AttemptAnswer"]] = relationship(back_populates="question")
