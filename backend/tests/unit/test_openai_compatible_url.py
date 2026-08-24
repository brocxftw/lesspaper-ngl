"""Tests for OpenAI-compatible URL normalization."""

from __future__ import annotations

import pytest

from lesspaper_ngl.ai.openai_compatible import _normalize_base_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1/"),
        ("https://api.openai.com/v1/", "https://api.openai.com/v1/"),
        ("https://api.openai.com", "https://api.openai.com/v1/"),
        ("https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1/"),
        ("http://host.docker.internal:1234/v1", "http://host.docker.internal:1234/v1/"),
        ("http://192.168.1.10:1234", "http://192.168.1.10:1234/v1/"),
    ],
)
def test_normalize_base_url(raw: str, expected: str) -> None:
    assert _normalize_base_url(raw) == expected
