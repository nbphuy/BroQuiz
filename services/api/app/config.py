from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://broquiz:broquiz_local_password@localhost:5432/broquiz"
    )
    upload_directory: Path = PROJECT_ROOT / "data" / "uploads"
    max_upload_size_bytes: int = 25 * 1024 * 1024
    chunk_size_chars: int = 1800
    chunk_overlap_chars: int = 250
    embedding_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "embeddinggemma"
    embedding_dimensions: int = 768
    embedding_batch_size: int = 16
    retrieval_top_k: int = 5
    retrieval_max_top_k: int = 20

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.chunk_size_chars <= 0:
            raise ValueError("chunk_size_chars must be positive")
        if not 0 <= self.chunk_overlap_chars < self.chunk_size_chars:
            raise ValueError("chunk_overlap_chars must be at least zero and less than chunk_size_chars")
        if self.embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be positive")
        if self.embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be positive")
        if not 1 <= self.retrieval_top_k <= self.retrieval_max_top_k:
            raise ValueError(
                "retrieval_top_k must be at least one and no greater than retrieval_max_top_k"
            )
        return self


settings = Settings()
