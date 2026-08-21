import logging
import math
import uuid
from dataclasses import dataclass
from numbers import Real

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embedding import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingResponseError,
    EmbeddingServiceUnavailable,
)
from app.services.embedding_service import get_embedding_provider


logger = logging.getLogger(__name__)


class RetrievalError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    page_number: int
    chunk_index: int
    similarity: float


def _embed_query(query: str, provider: EmbeddingProvider) -> list[float]:
    vectors = provider.embed_texts([query])
    if not isinstance(vectors, list) or len(vectors) != 1:
        raise EmbeddingResponseError("Embedding provider returned an unexpected vector count")
    vector = vectors[0]
    if not isinstance(vector, (list, tuple)) or len(vector) != settings.embedding_dimensions:
        raise EmbeddingResponseError("Embedding provider returned an invalid vector dimension")
    if any(
        not isinstance(value, Real)
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        for value in vector
    ):
        raise EmbeddingResponseError("Embedding provider returned a non-numeric vector value")
    return [float(value) for value in vector]


def retrieve_chunks(
    db: Session,
    document_id: uuid.UUID,
    query: str,
    top_k: int,
    provider: EmbeddingProvider | None = None,
) -> list[RetrievedChunk]:
    """Perform exact, document-scoped pgvector cosine-similarity retrieval."""
    document = db.get(Document, document_id)
    if document is None:
        raise RetrievalError(404, "Document not found.")
    if document.status != "embedded":
        raise RetrievalError(409, "Document is not embedded and cannot be searched.")

    try:
        chunk_count, embedded_count = db.execute(
            select(
                func.count(DocumentChunk.id),
                func.count(DocumentChunk.embedding),
            ).where(DocumentChunk.document_id == document.id)
        ).one()
        chunk_count, embedded_count = int(chunk_count), int(embedded_count)
    except SQLAlchemyError as exc:
        logger.exception("Failed to validate embedded chunks")
        raise RetrievalError(500, "Unable to search document chunks.") from exc
    if chunk_count == 0:
        raise RetrievalError(409, "Document has no embedded chunks to search.")
    if embedded_count != chunk_count:
        raise RetrievalError(409, "Document has incomplete embeddings.")

    try:
        provider = provider or get_embedding_provider()
        query_embedding = _embed_query(query, provider)
    except EmbeddingServiceUnavailable as exc:
        raise RetrievalError(503, "Embedding service unavailable.") from exc
    except EmbeddingProviderError as exc:
        logger.exception("Embedding provider returned an invalid query embedding")
        raise RetrievalError(500, "Embedding service returned an invalid response.") from exc
    except Exception as exc:
        logger.exception("Failed to create query embedding")
        raise RetrievalError(500, "Unable to create query embedding.") from exc

    distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("cosine_distance")
    statement = (
        select(DocumentChunk, distance)
        .where(
            DocumentChunk.document_id == document.id,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance.asc(), DocumentChunk.chunk_index.asc(), DocumentChunk.id.asc())
        .limit(top_k)
    )
    try:
        rows = db.execute(statement).all()
    except SQLAlchemyError as exc:
        logger.exception("Failed to retrieve document chunks")
        raise RetrievalError(500, "Unable to search document chunks.") from exc

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.content,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            similarity=1.0 - float(distance_value),
        )
        for chunk, distance_value in rows
    ]
