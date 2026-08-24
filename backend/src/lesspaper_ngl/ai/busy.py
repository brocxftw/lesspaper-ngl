"""Track providers with in-flight chat calls so health probes can defer."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_busy: set[uuid.UUID] = set()


def is_provider_busy(provider_id: uuid.UUID) -> bool:
    return provider_id in _busy


@asynccontextmanager
async def provider_chat_guard(provider_id: uuid.UUID) -> AsyncIterator[None]:
    _busy.add(provider_id)
    try:
        yield
    finally:
        _busy.discard(provider_id)
