import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.quiz import QuizResponse
from app.services.quiz_service import get_persisted_quiz

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz(quiz_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> QuizResponse:
    quiz = get_persisted_quiz(db, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found.")
    return quiz
