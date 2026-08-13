"""add quiz persistence

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("quizzes",
        sa.Column("id", sa.UUID(), nullable=False), sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(), nullable=False), sa.Column("topic", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="ready", nullable=False), sa.Column("generator_provider", sa.String(), nullable=False),
        sa.Column("generator_model", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_table("questions",
        sa.Column("id", sa.UUID(), nullable=False), sa.Column("quiz_id", sa.UUID(), nullable=False), sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("correct_answer", sa.Integer(), nullable=False), sa.Column("explanation", sa.Text(), nullable=False), sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("correct_answer >= 0 AND correct_answer <= 3", name="ck_questions_correct_answer_range"), sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("quiz_id", "position", name="uq_questions_quiz_id_position"))
    op.create_table("question_options",
        sa.Column("id", sa.UUID(), nullable=False), sa.Column("question_id", sa.UUID(), nullable=False), sa.Column("option_text", sa.Text(), nullable=False), sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0 AND position <= 3", name="ck_question_options_position_range"), sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("question_id", "position", name="uq_question_options_question_id_position"))
    op.create_table("question_sources",
        sa.Column("id", sa.UUID(), nullable=False), sa.Column("question_id", sa.UUID(), nullable=False), sa.Column("chunk_id", sa.UUID(), nullable=True), sa.Column("page_number", sa.Integer(), nullable=False), sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.CheckConstraint("page_number > 0", name="ck_question_sources_page_number_positive"), sa.CheckConstraint("chunk_index >= 0", name="ck_question_sources_chunk_index_nonnegative"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))


def downgrade() -> None:
    op.drop_table("question_sources")
    op.drop_table("question_options")
    op.drop_table("questions")
    op.drop_table("quizzes")
