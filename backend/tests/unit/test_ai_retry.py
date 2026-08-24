"""Unit tests for transient AI error classification and backoff."""

from __future__ import annotations

from lesspaper_ngl.ai.base import AIProviderError
from lesspaper_ngl.ai.retry import (
    adapter_retry_delay_seconds,
    is_transient_ai_error,
    job_retry_delay_seconds,
)


def test_detects_lm_studio_unload_and_cancel_messages() -> None:
    assert is_transient_ai_error(
        AIProviderError("Model was unloaded while the request was still in queue..", status_code=400)
    )
    assert is_transient_ai_error(
        AIProviderError(
            'Failed to load model "google/gemma-3-4b". Error: Operation canceled.',
            status_code=400,
        )
    )


def test_detects_retryable_http_statuses() -> None:
    assert is_transient_ai_error(AIProviderError("rate limited", status_code=429))
    assert is_transient_ai_error(AIProviderError("unavailable", status_code=503))
    assert not is_transient_ai_error(AIProviderError("bad request", status_code=400))


def test_non_provider_errors_are_not_transient() -> None:
    assert not is_transient_ai_error(ValueError("boom"))


def test_backoff_delays_grow_and_cap() -> None:
    assert adapter_retry_delay_seconds(1) == 1.0
    assert adapter_retry_delay_seconds(2) == 2.0
    assert adapter_retry_delay_seconds(3) == 4.0
    assert job_retry_delay_seconds(1) == 2.0
    assert job_retry_delay_seconds(2) == 4.0
    assert job_retry_delay_seconds(10) == 60.0
