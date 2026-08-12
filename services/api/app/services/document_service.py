import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.services.pdf_service import ExtractedPage, PdfExtractionError, extract_pdf_pages

if TYPE_CHECKING:
    from fastapi import UploadFile


logger = logging.getLogger(__name__)
PDF_SIGNATURE = b"%PDF-"
ALLOWED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
COPY_CHUNK_SIZE = 1024 * 1024


class DocumentUploadError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class ProcessedDocument:
    document: Document
    pages: list[ExtractedPage]


def _validate_upload_metadata(upload: "UploadFile") -> str:
    filename = (upload.filename or "").strip()
    if not filename:
        raise DocumentUploadError(400, "A file with a filename is required.")
    if not filename.lower().endswith(".pdf"):
        raise DocumentUploadError(415, "Only PDF files are supported.")
    if upload.content_type and upload.content_type.lower() not in ALLOWED_PDF_CONTENT_TYPES:
        raise DocumentUploadError(415, "Only PDF files are supported.")
    return filename


async def _save_upload(upload: "UploadFile", destination: Path) -> int:
    size = 0
    signature = b""
    try:
        with destination.open("xb") as output:
            while chunk := await upload.read(COPY_CHUNK_SIZE):
                size += len(chunk)
                if size > settings.max_upload_size_bytes:
                    raise DocumentUploadError(413, "The uploaded PDF exceeds the size limit.")
                if len(signature) < len(PDF_SIGNATURE):
                    signature += chunk[: len(PDF_SIGNATURE) - len(signature)]
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if size == 0:
        destination.unlink(missing_ok=True)
        raise DocumentUploadError(400, "The uploaded file is empty.")
    if signature != PDF_SIGNATURE:
        destination.unlink(missing_ok=True)
        raise DocumentUploadError(422, "The uploaded file is not a valid PDF.")
    return size


async def create_and_process_document(db: Session, upload: "UploadFile") -> ProcessedDocument:
    filename = _validate_upload_metadata(upload)
    settings.upload_directory.mkdir(parents=True, exist_ok=True)

    document = Document(filename=filename, content_type=upload.content_type, status="uploaded")
    db.add(document)
    try:
        db.flush()
        destination = settings.upload_directory / f"{document.id}.pdf"
        file_size = await _save_upload(upload, destination)
        document.file_size = file_size
        db.commit()
        db.refresh(document)
    except DocumentUploadError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Failed to save uploaded document")
        raise

    try:
        document.status = "processing"
        db.commit()
        pages = extract_pdf_pages(destination)
        document.page_count = len(pages)
        document.status = "processed"
        db.commit()
        db.refresh(document)
        return ProcessedDocument(document=document, pages=pages)
    except PdfExtractionError:
        db.rollback()
        document.status = "failed"
        db.commit()
        destination.unlink(missing_ok=True)
        raise DocumentUploadError(422, "The uploaded PDF could not be parsed or read.")
    except Exception:
        db.rollback()
        logger.exception("Unexpected document processing failure")
        try:
            document.status = "failed"
            db.commit()
        except Exception:
            db.rollback()
        destination.unlink(missing_ok=True)
        raise
