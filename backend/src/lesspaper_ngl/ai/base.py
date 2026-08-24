"""Shared AI adapter types and protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(slots=True)
class ChatResult:
    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(slots=True)
class EmbeddingResult:
    embeddings: list[list[float]]
    model: str
    input_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(slots=True)
class ModelCapabilities:
    supports_chat: bool = True
    supports_embeddings: bool = False
    supports_vision: bool = False
    context_window: int | None = None
    max_output_tokens: int | None = None


class AIProviderError(Exception):
    """Raised when an upstream AI provider returns an error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AIProviderAdapter(ABC):
    """Abstract adapter for chat and embedding providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier."""

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Whether requests stay on the local network."""

    @property
    @abstractmethod
    def capabilities(self) -> ModelCapabilities:
        """Advertised model capabilities."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        """Run a chat completion without tool calling."""

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        """Generate embeddings for one or more texts."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Return True when the provider responds successfully."""

    async def aclose(self) -> None:
        """Release network resources."""
