import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str | None
    file_size: int | None
    status: str
    page_count: int | None
    created_at: datetime
    updated_at: datetime


class DocumentChunkingResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    page_count: int
    chunk_count: int


class DocumentEmbeddingResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    chunk_count: int
    embedded_count: int
    model: str
    dimensions: int


class DocumentSearchRequest(BaseModel):
    query: Annotated[str, Field(min_length=1)]
    top_k: int = Field(default_factory=lambda: settings.retrieval_top_k)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, value: int) -> int:
        if not 1 <= value <= settings.retrieval_max_top_k:
            raise ValueError(
                f"top_k must be between 1 and {settings.retrieval_max_top_k}"
            )
        return value


class DocumentSearchResult(BaseModel):
    chunk_id: uuid.UUID
    page_number: int
    chunk_index: int
    content: str
    distance: float


class DocumentSearchResponse(BaseModel):
    document_id: uuid.UUID
    query: str
    top_k: int
    results: list[DocumentSearchResult]
