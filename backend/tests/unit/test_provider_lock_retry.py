"""Unit tests for local provider host locking and transient request retries."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from lesspaper_ngl.ai.base import AIProviderError
from lesspaper_ngl.ai.openai_compatible import OpenAICompatibleAdapter
from lesspaper_ngl.ai.provider_lock import lock_key_for_base_url, reset_provider_locks_for_tests


def _provider(*, is_local: bool = True) -> MagicMock:
    provider = MagicMock()
    provider.name = "lm-studio"
    provider.base_url = "http://192.168.1.109:1234/v1"
    provider.chat_model = "chat-model"
    provider.embedding_model = "embed-model"
    provider.max_output_tokens = 1024
    provider.supports_embeddings = True
    provider.supports_vision = False
    provider.context_window = 8192
    provider.is_local = is_local
    return provider


@pytest.fixture(autouse=True)
def _clear_locks() -> None:
    reset_provider_locks_for_tests()


def test_lock_key_uses_host_port() -> None:
    assert lock_key_for_base_url("http://192.168.1.109:1234/v1/") == "192.168.1.109:1234"
    assert lock_key_for_base_url("http://192.168.1.109:1234/v1") == "192.168.1.109:1234"


@pytest.mark.asyncio
async def test_local_requests_are_serialized_per_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lesspaper_ngl.ai.openai_compatible.adapter_retry_delay_seconds", lambda _a: 0)

    active = 0
    max_active = 0
    gate = asyncio.Event()
    started = 0

    async def slow_request(self, method, url, **kwargs):  # noqa: ANN001, ARG001
        nonlocal active, max_active, started
        started += 1
        if started == 1:
            gate.set()
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"ok": true}'
        response.json.return_value = {"ok": True}
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", slow_request)

    a = OpenAICompatibleAdapter(_provider(is_local=True))
    b = OpenAICompatibleAdapter(_provider(is_local=True))

    async def run_a() -> object:
        return await a._request("GET", "models")

    async def run_b() -> object:
        await gate.wait()
        return await b._request("GET", "models")

    await asyncio.gather(run_a(), run_b())
    assert max_active == 1
    await a.aclose()
    await b.aclose()


@pytest.mark.asyncio
async def test_retries_transient_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lesspaper_ngl.ai.openai_compatible.adapter_retry_delay_seconds", lambda _a: 0)
    adapter = OpenAICompatibleAdapter(_provider(is_local=False))
    calls = {"n": 0}

    async def flaky_once(
        method: str,
        path: str,
        *,
        payload: dict | None = None,
    ) -> dict:
        calls["n"] += 1
        if calls["n"] < 3:
            raise AIProviderError(
                "Model was unloaded while the request was still in queue..",
                status_code=400,
            )
        return {"data": []}

    adapter._request_once = AsyncMock(side_effect=flaky_once)  # type: ignore[method-assign]
    data = await adapter._request("POST", "embeddings", payload={"input": "x"})
    assert data == {"data": []}
    assert calls["n"] == 3
    await adapter.aclose()


@pytest.mark.asyncio
async def test_does_not_retry_permanent_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lesspaper_ngl.ai.openai_compatible.adapter_retry_delay_seconds", lambda _a: 0)
    adapter = OpenAICompatibleAdapter(_provider(is_local=False))
    adapter._request_once = AsyncMock(  # type: ignore[method-assign]
        side_effect=AIProviderError("invalid api key", status_code=401)
    )
    with pytest.raises(AIProviderError, match="invalid api key"):
        await adapter._request("POST", "embeddings", payload={"input": "x"})
    assert adapter._request_once.await_count == 1
    await adapter.aclose()
