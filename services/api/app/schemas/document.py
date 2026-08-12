import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
