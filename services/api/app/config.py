from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://broquiz:broquiz_local_password@localhost:5432/broquiz"
    )
    upload_directory: Path = PROJECT_ROOT / "data" / "uploads"
    max_upload_size_bytes: int = 25 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
