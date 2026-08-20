import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.pdf_service import ExtractedPage, PdfExtractionError, extract_pdf_pages


logger = logging.getLogger(__name__)
_EXCESS_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_SENTENCE_BOUNDARY = re.compile(r"[.!?][\"')\]]?(?:\s+|$)")


@dataclass(frozen=True)
class TextChunk:
    content: str
    page_number: int
    chunk_index: int


@dataclass(frozen=True)
class ChunkingResult:
    document: Document
    page_count: int
    chunk_count: int


class DocumentChunkingError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def normalize_page_text(text: str) -> str:
    """Apply conservative whitespace normalization to extracted PDF page text."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return _EXCESS_BLANK_LINES.sub("\n\n", normalized)


def _last_boundary(text: str, start: int, limit: int) -> int:
    """Return a preferred boundary close to limit, or the hard limit."""
    minimum_preferred = start + max(1, int((limit - start) * 0.6))
    window = text[start:limit]

    for marker in ("\n\n", "\n"):
        index = window.rfind(marker)
        if index >= 0:
            boundary = start + index + len(marker)
            if boundary >= minimum_preferred:
                return boundary

    sentence_boundaries = [start + match.end() for match in _SENTENCE_BOUNDARY.finditer(window)]
    preferred_sentences = [boundary for boundary in sentence_boundaries if boundary >= minimum_preferred]
    if preferred_sentences:
        return preferred_sentences[-1]

    whitespace = [match.start() for match in re.finditer(r"\s+", window)]
    preferred_whitespace = [start + index for index in whitespace if start + index >= minimum_preferred]
    if preferred_whitespace:
        return preferred_whitespace[-1]
    return limit


def chunk_page_text(text: str, page_number: int, *, chunk_size: int, overlap: int) -> list[tuple[str, int]]:
    """Split one page without crossing its boundary, always respecting chunk_size."""
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller than chunk_size")

    normalized = normalize_page_text(text)
    if not normalized:
        return []

    chunks: list[tuple[str, int]] = []
    start = 0
    length = len(normalized)
    while start < length:
        limit = min(start + chunk_size, length)
        end = length if limit == length else _last_boundary(normalized, start, limit)
        if end <= start:
            end = limit

        content = normalized[start:end].strip()
        if content:
            chunks.append((content, page_number))
        if end == length:
            break

        next_start = max(start + 1, end - overlap)
        while next_start < length and normalized[next_start].isspace():
            next_start += 1
        start = next_start
    return chunks


def chunk_extracted_pages(
    pages: list[ExtractedPage], *, chunk_size: int | None = None, overlap: int | None = None
) -> list[TextChunk]:
    """Create deterministic, globally indexed chunks while retaining each source page."""
    chunk_size = settings.chunk_size_chars if chunk_size is None else chunk_size
    overlap = settings.chunk_overlap_chars if overlap is None else overlap
    chunks: list[TextChunk] = []
    for page in pages:
        for content, page_number in chunk_page_text(
            page.text, page.page_number, chunk_size=chunk_size, overlap=overlap
        ):
            chunks.append(
                TextChunk(content=content, page_number=page_number, chunk_index=len(chunks))
            )
    return chunks


def chunk_document(db: Session, document_id: uuid.UUID) -> ChunkingResult:
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentChunkingError(404, "Document not found.")
    if document.status == "chunked":
        existing_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document.id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        return ChunkingResult(
            document=document,
            page_count=document.page_count or 0,
            chunk_count=len(existing_chunks),
        )
    if document.status != "processed":
        raise DocumentChunkingError(409, "Document is not ready for chunking.")

    pdf_path = Path(settings.upload_directory) / f"{document.id}.pdf"
    if not pdf_path.is_file():
        raise DocumentChunkingError(409, "The stored PDF is unavailable.")

    try:
        pages = extract_pdf_pages(pdf_path)
    except PdfExtractionError as exc:
        logger.exception("Stored PDF could not be extracted for chunking")
        raise DocumentChunkingError(500, "Unable to read the stored PDF.") from exc

    chunks = chunk_extracted_pages(pages)
    try:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        db.add_all(
            [
                DocumentChunk(
                    document_id=document.id,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                )
                for chunk in chunks
            ]
        )
        document.status = "chunked"
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        logger.exception("Failed to persist document chunks")
        raise

    return ChunkingResult(document=document, page_count=len(pages), chunk_count=len(chunks))
