import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentUploadError, create_and_process_document


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File(description="Text-based PDF document")],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentResponse:
    try:
        result = await create_and_process_document(db, file)
    except DocumentUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        logger.exception("Unexpected document upload error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process the uploaded document.",
        )
    return DocumentResponse.model_validate(result.document)
