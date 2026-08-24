"""Tests for worker OCR exclusive gate."""

from __future__ import annotations

import asyncio

import pytest

from lesspaper_ngl.workers import ocr_gate


@pytest.mark.asyncio
async def test_ocr_exclusive_lock_blocks_overlap() -> None:
    assert ocr_gate.ocr_exclusive_locked() is False

    async with ocr_gate.ocr_exclusive_section():
        assert ocr_gate.ocr_exclusive_locked() is True

        acquired = asyncio.Event()

        async def _waiter() -> None:
            async with ocr_gate.ocr_exclusive_section():
                acquired.set()

        task = asyncio.create_task(_waiter())
        await asyncio.sleep(0.05)
        assert not acquired.is_set()
        assert ocr_gate.ocr_exclusive_locked() is True

    await asyncio.wait_for(acquired.wait(), timeout=1.0)
    await task
    assert ocr_gate.ocr_exclusive_locked() is False
