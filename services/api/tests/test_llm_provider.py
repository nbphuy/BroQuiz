from types import SimpleNamespace

import pytest

from app.schemas.quiz import GeneratedQuiz
from app.services.llm import LLMServiceUnavailable, LLMStructuredOutputError
from app.services.llm.ollama_provider import OllamaLLMProvider


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_ollama_provider_passes_pydantic_schema_and_validates_json() -> None:
    content = '{"title":"Quiz","questions":[{"question":"Q","options":["A","B","C","D"],"correct_answer":0,"explanation":"E","sources":[{"chunk_id":"00000000-0000-0000-0000-000000000001","page_number":1}]}]}'
    client = FakeClient(SimpleNamespace(message=SimpleNamespace(content=content)))
    result = OllamaLLMProvider(client).generate_structured([{"role": "user", "content": "test"}], GeneratedQuiz)
    assert result.title == "Quiz"
    assert client.calls[0]["format"] == GeneratedQuiz.model_json_schema()
    assert client.calls[0]["stream"] is False
    assert client.calls[0]["think"] is False


def test_ollama_provider_rejects_malformed_structured_output_and_maps_connection_errors() -> None:
    malformed = OllamaLLMProvider(FakeClient(SimpleNamespace(message=SimpleNamespace(content="not json"))))
    with pytest.raises(LLMStructuredOutputError):
        malformed.generate_structured([], GeneratedQuiz)
    unavailable = OllamaLLMProvider(FakeClient(error=ConnectionError("private details")))
    with pytest.raises(LLMServiceUnavailable):
        unavailable.generate_structured([], GeneratedQuiz)
