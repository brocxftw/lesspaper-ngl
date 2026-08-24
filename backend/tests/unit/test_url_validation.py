"""Provider base URL validation unit tests."""

from __future__ import annotations

import pytest

from lesspaper_ngl.ai.url_validation import validate_provider_base_url
from lesspaper_ngl.core.exceptions import ValidationError


def test_accepts_localhost_http() -> None:
    result = validate_provider_base_url("http://localhost:11434")
    assert result.url == "http://localhost:11434"
    assert result.is_local is True
    assert result.hostname == "localhost"


def test_accepts_https_remote_host() -> None:
    result = validate_provider_base_url("https://api.openai.com/v1")
    assert result.is_local is False
    assert result.scheme == "https"


def test_rejects_empty_url() -> None:
    with pytest.raises(ValidationError):
        validate_provider_base_url("")


def test_rejects_non_http_scheme() -> None:
    with pytest.raises(ValidationError):
        validate_provider_base_url("ftp://localhost/models")


def test_rejects_embedded_credentials() -> None:
    with pytest.raises(ValidationError):
        validate_provider_base_url("http://user:pass@localhost:8080")
