"""lesspaper-ngl AI integration layer."""

from __future__ import annotations

from lesspaper_ngl.ai.base import (
    AIProviderAdapter,
    AIProviderError,
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ModelCapabilities,
)
from lesspaper_ngl.ai.privacy import PrivacyGate
from lesspaper_ngl.ai.profiles import ContextBudget, ProfileLimits, compute_budget, resolve_profile
from lesspaper_ngl.ai.rag import AskResult, Citation, RAGScope, ask
from lesspaper_ngl.ai.registry import get_adapter
from lesspaper_ngl.ai.url_validation import ValidatedProviderURL, validate_provider_base_url
from lesspaper_ngl.ai.usage import record_usage

__all__ = [
    "AIProviderAdapter",
    "AIProviderError",
    "AskResult",
    "ChatMessage",
    "ChatResult",
    "Citation",
    "ContextBudget",
    "EmbeddingResult",
    "ModelCapabilities",
    "PrivacyGate",
    "ProfileLimits",
    "RAGScope",
    "ValidatedProviderURL",
    "ask",
    "compute_budget",
    "get_adapter",
    "record_usage",
    "resolve_profile",
    "validate_provider_base_url",
]
