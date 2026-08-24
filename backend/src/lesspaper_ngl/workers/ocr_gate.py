"""Exclusive gate so OCR does not overlap other worker jobs in-process.

When ``JOB_CONCURRENCY`` is greater than 1, OCR still takes exclusive access:
``_poll_jobs`` skips claiming while the gate is held.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_ocr_exclusive = asyncio.Lock()


def ocr_exclusive_locked() -> bool:
    """True while an OCR section is held (or waiting to be acquired)."""
    return _ocr_exclusive.locked()


@asynccontextmanager
async def ocr_exclusive_section() -> AsyncIterator[None]:
    """Hold exclusive OCR capacity for the duration of Paddle work."""
    async with _ocr_exclusive:
        yield
