import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embedding import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingResponseError,
    EmbeddingServiceUnavailable,
    OllamaEmbeddingProvider,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingResult:
    document: Document
    chunk_count: int
    embedded_count: int


class DocumentEmbeddingError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider.lower() == "ollama":
        return OllamaEmbeddingProvider()
    raise DocumentEmbeddingError(500, "Embedding provider is not configured.")


def embed_document(
    db: Session, document_id: uuid.UUID, provider: EmbeddingProvider | None = None
) -> EmbeddingResult:
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentEmbeddingError(404, "Document not found.")
    if document.status not in {"chunked", "embedded"}:
        raise DocumentEmbeddingError(409, "Document is not ready for embedding.")

    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
        )
    )
    if not chunks:
        raise DocumentEmbeddingError(409, "Document has no chunks to embed.")

    provider = provider or get_embedding_provider()
    try:
        for start in range(0, len(chunks), settings.embedding_batch_size):
            batch = chunks[start : start + settings.embedding_batch_size]
            vectors = provider.embed_texts([chunk.content for chunk in batch])
            if len(vectors) != len(batch):
                raise EmbeddingResponseError("Embedding provider returned an unexpected vector count")
            for chunk, vector in zip(batch, vectors, strict=True):
                # Providers validate vectors, but retain this boundary check for future adapters.
                if len(vector) != settings.embedding_dimensions:
                    raise EmbeddingResponseError("Embedding provider returned an invalid vector dimension")
                chunk.embedding = vector

        document.status = "embedded"
        db.commit()
        db.refresh(document)
    except EmbeddingServiceUnavailable as exc:
        db.rollback()
        raise DocumentEmbeddingError(503, "Embedding service unavailable") from exc
    except EmbeddingProviderError as exc:
        db.rollback()
        logger.exception("Embedding provider returned an invalid response")
        raise DocumentEmbeddingError(500, "Embedding service returned an invalid response.") from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to persist document embeddings")
        raise DocumentEmbeddingError(500, "Unable to store document embeddings.") from exc

    return EmbeddingResult(document=document, chunk_count=len(chunks), embedded_count=len(chunks))
