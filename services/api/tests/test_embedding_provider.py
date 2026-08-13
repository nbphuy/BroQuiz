from types import SimpleNamespace

import pytest

from app.services.embedding import EmbeddingResponseError
from app.services.embedding.ollama_provider import OllamaEmbeddingProvider


class FakeClient:
    def __init__(self, embeddings):
        self.embeddings = embeddings
        self.calls = []

    def embed(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(embeddings=self.embeddings)


def test_zero_texts_returns_zero_vectors_without_calling_ollama() -> None:
    client = FakeClient([])
    assert OllamaEmbeddingProvider(client).embed_texts([]) == []
    assert client.calls == []


def test_vector_count_must_match_input_count() -> None:
    provider = OllamaEmbeddingProvider(FakeClient([[0.0] * 768]))
    with pytest.raises(EmbeddingResponseError):
        provider.embed_texts(["one", "two"])


def test_invalid_vector_dimensions_are_rejected() -> None:
    provider = OllamaEmbeddingProvider(FakeClient([[0.0] * 767]))
    with pytest.raises(EmbeddingResponseError):
        provider.embed_texts(["one"])


def test_provider_requests_configured_model_and_dimensions() -> None:
    client = FakeClient([[0.0] * 768])
    assert OllamaEmbeddingProvider(client).embed_texts(["one"]) == [[0.0] * 768]
    assert client.calls[0]["model"] == "embeddinggemma"
    assert client.calls[0]["dimensions"] == 768
