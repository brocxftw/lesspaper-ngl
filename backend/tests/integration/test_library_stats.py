"""Library activity counters, overview API, and tag merge tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import Job, JobType, LibraryActivityCounters, User
from lesspaper_ngl.services import tags as tag_service
from lesspaper_ngl.workers.processor import mark_preflight_ready, process_text_extraction


async def _admin_user_id(db_session: AsyncSession) -> uuid.UUID:
    admin = (
        await db_session.execute(select(User).where(User.username == "admin"))
    ).scalar_one()
    return admin.id


@pytest.mark.asyncio
async def test_library_counters_on_ingest_and_reset(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    admin_id = await _admin_user_id(db_session)
    overview_before = await auth_client.get("/api/library/overview")
    assert overview_before.status_code == 200, overview_before.text
    before = overview_before.json()
    assert before["activity"]["documents_ingested"] == 0

    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("library-counter.txt", fh, "text/plain")},
        )
    assert response.status_code == 201, response.text

    overview_after = await auth_client.get("/api/library/overview")
    assert overview_after.status_code == 200
    after = overview_after.json()
    assert after["activity"]["documents_ingested"] >= 1
    assert after["activity"]["bytes_ingested"] > 0
    assert after["snapshot"]["current_documents"] >= 1

    reset = await auth_client.post("/api/library/reset-statistics")
    assert reset.status_code == 200, reset.text
    reset_body = reset.json()
    assert reset_body["documents_ingested"] == 0
    assert reset_body["bytes_ingested"] == 0

    row = await db_session.get(LibraryActivityCounters, admin_id)
    assert row is not None
    assert int(row.documents_ingested) == 0


@pytest.mark.asyncio
async def test_duplicate_rejected_increments_counter(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        first = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("dup-lib.txt", fh, "text/plain")},
        )
    assert first.status_code == 201

    with sample_txt_path.open("rb") as fh:
        second = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("dup-lib.txt", fh, "text/plain")},
            data={"on_duplicate": "skip"},
        )
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"

    overview = await auth_client.get("/api/library/overview")
    assert overview.status_code == 200
    assert overview.json()["activity"]["duplicates_rejected"] >= 1


@pytest.mark.asyncio
async def test_inbox_overview_uses_historical_counters(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("inbox-hist.txt", fh, "text/plain")},
        )
    assert response.status_code == 201
    doc_id = response.json()["id"]

    extract_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == uuid.UUID(doc_id),
                Job.job_type == JobType.TEXT_EXTRACTION,
            )
        )
    ).scalar_one()
    await process_text_extraction(db_session, extract_job)
    await mark_preflight_ready(db_session, uuid.UUID(doc_id))
    await db_session.commit()

    overview = await auth_client.get("/api/inbox/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["total_ingested"] >= 1
    assert body["processed"] >= 1
    assert body["processing"] >= 0


@pytest.mark.asyncio
async def test_tag_merge(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin_id = await _admin_user_id(db_session)
    source = await tag_service.create_tag(db_session, "Merge Source", admin_id, "#9333EA")
    target = await tag_service.create_tag(db_session, "Merge Target", admin_id, "#16A34A")
    await db_session.commit()

    response = await auth_client.post(
        "/api/tags/merge",
        json={"source_tag_id": str(source.id), "target_tag_id": str(target.id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Merge Target"

    tags = await auth_client.get("/api/tags")
    assert tags.status_code == 200
    names = {t["name"] for t in tags.json()}
    assert "Merge Source" not in names
    assert "Merge Target" in names


@pytest.mark.asyncio
async def test_purge_increments_counter(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        created = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("purge-lib.txt", fh, "text/plain")},
        )
    assert created.status_code == 201
    doc_id = created.json()["id"]

    removed = await auth_client.post(
        f"/api/documents/{doc_id}/remove-from-queue",
    )
    assert removed.status_code == 200, removed.text

    overview = await auth_client.get("/api/library/overview")
    assert overview.status_code == 200
    assert overview.json()["activity"]["purged_documents"] >= 1
    # Historical ingest count must not decrease after purge.
    assert overview.json()["activity"]["documents_ingested"] >= 1
