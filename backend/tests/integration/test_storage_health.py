"""Storage health integration tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.db.session import dispose_engine
from lesspaper_ngl.main import app
from lesspaper_ngl.storage.service import StorageService
from tests.conftest import login


@pytest.mark.asyncio
async def test_missing_path_returns_degraded(
    storage_root: Path,
    restore_storage_paths: None,
) -> None:
    missing = storage_root / "definitely-missing-docs"
    assert not missing.exists()
    os.environ["DOCUMENTS_PATH"] = str(missing)
    os.environ["CONSUME_PATH"] = str(storage_root / "consume")
    os.environ["EXPORT_PATH"] = str(storage_root / "export")
    get_settings.cache_clear()

    health = StorageService().check_health()
    assert health.documents_ok is False
    assert health.status in {"degraded", "unavailable"}

    await dispose_engine()
    get_settings.cache_clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/storage")
    assert response.status_code == 200
    body = response.json()
    assert body["documents_ok"] is False
    assert body["status"] in {"degraded", "unavailable"}


@pytest.mark.asyncio
async def test_writes_rejected_when_storage_unavailable(
    db_session,
    storage_root: Path,
    sample_txt_path: Path,
    restore_storage_paths: None,
) -> None:
    del db_session
    blocker = storage_root / "not-a-directory"
    blocker.write_text("blocked", encoding="utf-8")
    bad_docs = blocker / "documents"
    os.environ["DOCUMENTS_PATH"] = str(bad_docs)
    os.environ["CONSUME_PATH"] = str(storage_root / "consume")
    os.environ["EXPORT_PATH"] = str(storage_root / "export")
    get_settings.cache_clear()

    storage = StorageService()
    with pytest.raises(Exception) as exc_info:
        await storage.persist_original(
            b"data",
            checksum=storage.sha256_bytes(b"data"),
            extension="txt",
        )
    assert exc_info.value.__class__.__name__ == "StorageUnavailableError"

    await dispose_engine()
    get_settings.cache_clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await login(client)
        with sample_txt_path.open("rb") as fh:
            upload = await client.post(
                "/api/documents/upload",
                files={"file": ("sample.txt", fh, "text/plain")},
            )
    assert upload.status_code == 503
