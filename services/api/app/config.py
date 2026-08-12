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

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> "Settings":
        if self.chunk_size_chars <= 0:
            raise ValueError("chunk_size_chars must be positive")
        if not 0 <= self.chunk_overlap_chars < self.chunk_size_chars:
            raise ValueError("chunk_overlap_chars must be at least zero and less than chunk_size_chars")
        return self


settings = Settings()
