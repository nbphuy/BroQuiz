from abc import ABC, abstractmethod


class EmbeddingProviderError(Exception):
    """Base class for safe embedding-provider failures."""


class EmbeddingServiceUnavailable(EmbeddingProviderError):
    """The configured embedding service could not be reached."""


class EmbeddingResponseError(EmbeddingProviderError):
    """The provider returned data that cannot be stored safely."""


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one validated embedding vector per input text."""
