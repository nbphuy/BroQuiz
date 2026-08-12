from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfExtractionError(Exception):
    """Raised when a PDF cannot be read as a text-based BroQuiz document."""


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


def extract_pdf_pages(path: Path) -> list[ExtractedPage]:
    """Open a PDF and return its text page-by-page using 1-based page numbers."""
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise PdfExtractionError("Encrypted PDFs are not supported.")
        return [
            ExtractedPage(page_number=index, text=page.extract_text() or "")
            for index, page in enumerate(reader.pages, start=1)
        ]
    except PdfExtractionError:
        raise
    except (PdfReadError, OSError, ValueError, KeyError) as exc:
        raise PdfExtractionError("The PDF could not be parsed.") from exc
