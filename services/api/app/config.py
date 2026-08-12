from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://broquiz:broquiz_local_password@localhost:5432/broquiz"
    )

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
