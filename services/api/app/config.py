from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EMBEDDING_VECTOR_DIMENSIONS = 768


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
    embedding_dimensions: int = EMBEDDING_VECTOR_DIMENSIONS
    embedding_batch_size: int = 16
    retrieval_top_k: int = 5
    retrieval_max_top_k: int = 20
    llm_provider: str = "ollama"
    ollama_llm_model: str = "qwen3:1.7b"
    quiz_retrieval_top_k: int = 5
    quiz_default_question_count: int = 5
    quiz_max_question_count: int = 10

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
        if self.embedding_dimensions != EMBEDDING_VECTOR_DIMENSIONS:
            raise ValueError(
                "embedding_dimensions must match the persisted pgvector schema "
                f"({EMBEDDING_VECTOR_DIMENSIONS})"
            )
        if self.embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be positive")
        if not 1 <= self.retrieval_top_k <= self.retrieval_max_top_k:
            raise ValueError(
                "retrieval_top_k must be at least one and no greater than retrieval_max_top_k"
            )
        if self.llm_provider.lower() != "ollama":
            raise ValueError("llm_provider must be ollama")
        if not self.ollama_llm_model.strip():
            raise ValueError("ollama_llm_model must not be empty")
        if self.quiz_retrieval_top_k <= 0:
            raise ValueError("quiz_retrieval_top_k must be positive")
        if not 1 <= self.quiz_default_question_count <= self.quiz_max_question_count:
            raise ValueError(
                "quiz_default_question_count must be at least one and no greater than quiz_max_question_count"
            )
        return self


settings = Settings()
