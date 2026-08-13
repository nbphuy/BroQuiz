import math
from numbers import Real
from typing import Any

import ollama

from app.config import settings
from app.services.embedding.base import (
    EmbeddingProvider,
    EmbeddingResponseError,
    EmbeddingServiceUnavailable,
)


class OllamaEmbeddingProvider(EmbeddingProvider):
    """EmbeddingGemma adapter for a locally running Ollama instance."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or ollama.Client(host=settings.ollama_base_url)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            response = self._client.embed(
                model=settings.embedding_model,
                input=texts,
                dimensions=settings.embedding_dimensions,
            )
        except Exception as exc:
            # The route intentionally maps this to a safe 503 message.
            raise EmbeddingServiceUnavailable("Embedding service unavailable") from exc

        embeddings = getattr(response, "embeddings", None)
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbeddingResponseError("Embedding provider returned an unexpected vector count")

        validated: list[list[float]] = []
        for vector in embeddings:
            if not isinstance(vector, (list, tuple)) or len(vector) != settings.embedding_dimensions:
                raise EmbeddingResponseError("Embedding provider returned an invalid vector dimension")
            if any(
                not isinstance(value, Real)
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in vector
            ):
                raise EmbeddingResponseError("Embedding provider returned a non-numeric vector value")
            validated.append([float(value) for value in vector])
        return validated

    def validate_connection(self) -> None:
        """Confirm the local model responds with a correctly sized embedding."""
        self.embed_texts(["BroQuiz embedding connectivity check"])
