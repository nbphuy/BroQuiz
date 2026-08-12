import logging

from fastapi import FastAPI, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.database import check_database_connection
from app.api.documents import router as documents_router


logger = logging.getLogger(__name__)

app = FastAPI(title="BroQuiz API", version="0.1.0")
app.include_router(documents_router)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        check_database_connection()
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    return {"status": "ok", "database": "ok"}
