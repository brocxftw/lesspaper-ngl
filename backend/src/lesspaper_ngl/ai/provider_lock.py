"""Serialize requests to the same local AI provider host.

Local OpenAI-compatible servers (LM Studio, Ollama, etc.) often load one model
at a time. Concurrent chat + embedding calls against the same host cause model
unload/cancel races. A process-wide lock keyed by host prevents that thrash.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

_locks: dict[str, asyncio.Lock] = {}
_meta_lock = asyncio.Lock()


def lock_key_for_base_url(base_url: str) -> str:
    """Return a stable lock key for a provider base URL (usually host:port)."""
    raw = base_url.strip()
    parsed = urlparse(raw)
    netloc = (parsed.netloc or "").lower()
    if netloc:
        return netloc
    return raw.rstrip("/").lower() or "default"


async def _get_lock(key: str) -> asyncio.Lock:
    async with _meta_lock:
        lock = _locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _locks[key] = lock
        return lock


@asynccontextmanager
async def provider_host_lock(base_url: str) -> AsyncIterator[None]:
    """Hold an exclusive lock for all requests to this provider host."""
    lock = await _get_lock(lock_key_for_base_url(base_url))
    async with lock:
        yield


def reset_provider_locks_for_tests() -> None:
    """Clear lock registry between unit tests."""
    _locks.clear()
