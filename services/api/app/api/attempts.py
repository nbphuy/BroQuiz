import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.quiz import AttemptInProgressResponse, AttemptSubmissionRequest, AttemptSubmittedResponse
from app.services.attempt_service import AttemptError, get_attempt, submit_attempt

router = APIRouter(prefix="/attempts", tags=["attempts"])


@router.get("/{attempt_id}", response_model=AttemptInProgressResponse | AttemptSubmittedResponse)
def get_quiz_attempt(attempt_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    attempt = get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found.")
    return attempt


@router.post("/{attempt_id}/submit", response_model=AttemptSubmittedResponse)
def submit_quiz_attempt(attempt_id: uuid.UUID, request: AttemptSubmissionRequest, db: Annotated[Session, Depends(get_db)]) -> AttemptSubmittedResponse:
    try:
        return submit_attempt(db, attempt_id, request.answers)
    except AttemptError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
