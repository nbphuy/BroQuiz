import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.schemas.document import (
    DocumentChunkingResponse,
    DocumentEmbeddingResponse,
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentSearchResult,
)
from app.schemas.quiz import QuizGenerationRequest, QuizGenerationResponse
from app.services.chunking_service import DocumentChunkingError, chunk_document
from app.services.document_service import DocumentUploadError, create_and_process_document
from app.services.embedding_service import DocumentEmbeddingError, embed_document
from app.services.retrieval_service import RetrievalError, retrieve_chunks
from app.services.quiz_service import QuizGenerationError, generate_quiz


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File(description="Text-based PDF document")],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentResponse:
    try:
        document = await create_and_process_document(db, file)
    except DocumentUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        logger.exception("Unexpected document upload error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process the uploaded document.",
        )
    return DocumentResponse.model_validate(document)


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


@router.post("/{document_id}/embeddings", response_model=DocumentEmbeddingResponse)
def create_document_embeddings(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentEmbeddingResponse:
    try:
        result = embed_document(db, document_id)
    except DocumentEmbeddingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        logger.exception("Unexpected document embedding error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate document embeddings.",
        )
    return DocumentEmbeddingResponse(
        document_id=result.document.id,
        status=result.document.status,
        chunk_count=result.chunk_count,
        embedded_count=result.embedded_count,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )


@router.post("/{document_id}/search", response_model=DocumentSearchResponse)
def search_document(
    document_id: uuid.UUID,
    request: DocumentSearchRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentSearchResponse:
    try:
        results = retrieve_chunks(db, document_id, request.query, request.top_k)
    except RetrievalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        logger.exception("Unexpected semantic retrieval error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to search document chunks.",
        )

    return DocumentSearchResponse(
        document_id=document_id,
        query=request.query,
        top_k=request.top_k,
        results=[
            DocumentSearchResult(
                chunk_id=result.chunk_id,
                page_number=result.page_number,
                chunk_index=result.chunk_index,
                content=result.content,
                distance=result.cosine_distance,
            )
            for result in results
        ],
    )


@router.post("/{document_id}/quiz/generate", response_model=QuizGenerationResponse)
def generate_document_quiz(
    document_id: uuid.UUID,
    request: QuizGenerationRequest,
    db: Annotated[Session, Depends(get_db)],
) -> QuizGenerationResponse:
    try:
        return generate_quiz(db, document_id, request.topic, request.question_count)
    except QuizGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception:
        logger.exception("Unexpected quiz generation error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate quiz.",
        )
