import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.document import DocumentChunkingResponse, DocumentResponse
from app.services.chunking_service import DocumentChunkingError, chunk_document
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


@router.post("/{document_id}/chunks", response_model=DocumentChunkingResponse)
def create_document_chunks(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentChunkingResponse:
    try:
        result = chunk_document(db, document_id)
    except DocumentChunkingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        logger.exception("Unexpected document chunking error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate document chunks.",
        )
    return DocumentChunkingResponse(
        document_id=result.document.id,
        status=result.document.status,
        page_count=result.page_count,
        chunk_count=result.chunk_count,
    )
