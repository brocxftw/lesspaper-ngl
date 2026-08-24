"""Unit tests for provider busy tracking and health probe deferral."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lesspaper_ngl.ai.busy import is_provider_busy, provider_chat_guard
from lesspaper_ngl.ai.health import probe_provider


@pytest.mark.asyncio
async def test_provider_chat_guard_marks_busy() -> None:
    provider_id = uuid.uuid4()
    assert not is_provider_busy(provider_id)
    async with provider_chat_guard(provider_id):
        assert is_provider_busy(provider_id)
    assert not is_provider_busy(provider_id)


@pytest.mark.asyncio
async def test_probe_skips_busy_provider() -> None:
    provider_id = uuid.uuid4()
    provider = SimpleNamespace(id=provider_id, name="busy-llm")
    async with provider_chat_guard(provider_id):
        with patch("lesspaper_ngl.ai.health.get_adapter") as get_adapter:
            await probe_provider(provider)  # type: ignore[arg-type]
            get_adapter.assert_not_called()
