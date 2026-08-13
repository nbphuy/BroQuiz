from abc import ABC, abstractmethod
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class LLMProviderError(Exception):
    """Base class for safe LLM-provider failures."""


class LLMServiceUnavailable(LLMProviderError):
    """The configured LLM service or model could not be reached."""


class LLMStructuredOutputError(LLMProviderError):
    """The provider did not return schema-valid structured content."""


class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(
        self, messages: Sequence[dict[str, str]], response_model: type[ResponseModel]
    ) -> ResponseModel:
        """Generate and validate a response matching the supplied Pydantic model."""
