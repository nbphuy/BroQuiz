from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def check_database_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
