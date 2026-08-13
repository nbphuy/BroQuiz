from typing import Any, Sequence

import ollama
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.services.llm.base import (
    LLMProvider,
    LLMServiceUnavailable,
    LLMStructuredOutputError,
    ResponseModel,
)


class OllamaLLMProvider(LLMProvider):
    """Structured-output adapter for the local Ollama generative model."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or ollama.Client(host=settings.ollama_base_url)

    def generate_structured(
        self, messages: Sequence[dict[str, str]], response_model: type[ResponseModel]
    ) -> ResponseModel:
        try:
            response = self._client.chat(
                model=settings.ollama_llm_model,
                messages=list(messages),
                format=response_model.model_json_schema(),
                stream=False,
                think=False,
            )
        except Exception as exc:
            raise LLMServiceUnavailable("LLM service unavailable") from exc

        message = getattr(response, "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise LLMStructuredOutputError("LLM returned no structured content")
        try:
            return response_model.model_validate_json(content)
        except ValidationError as exc:
            raise LLMStructuredOutputError("LLM returned invalid structured content") from exc
