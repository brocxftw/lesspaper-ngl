"""Inbox review-and-filing queue integration tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import Job, JobType, ProcessingStatus
from lesspaper_ngl.workers.processor import process_text_extraction


@pytest.mark.asyncio
async def test_upload_does_not_enqueue_indexing(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert response.status_code == 201, response.text
    doc_id = uuid.UUID(response.json()["id"])

    jobs = (
        await db_session.execute(select(Job).where(Job.document_id == doc_id))
    ).scalars().all()
    types = {j.job_type for j in jobs}
    assert JobType.TEXT_EXTRACTION in types
    assert JobType.THUMBNAIL in types
    assert JobType.INDEXING not in types


@pytest.mark.asyncio
async def test_preflight_marks_ready_without_indexing(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    doc_id = uuid.UUID(response.json()["id"])

    extract_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.TEXT_EXTRACTION,
            )
        )
    ).scalar_one()
    await process_text_extraction(db_session, extract_job)
    await db_session.commit()

    detail = await auth_client.get(f"/api/documents/{doc_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["inbox"] is True
    assert body["processing_status"] == ProcessingStatus.READY.value
    assert body["inbox_status"] == "needs_review"
    assert body["document_indexed"] is False

    jobs = (
        await db_session.execute(select(Job).where(Job.document_id == doc_id))
    ).scalars().all()
    assert JobType.INDEXING not in {j.job_type for j in jobs}


@pytest.mark.asyncio
async def test_process_leaves_inbox_and_enqueues_indexing(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
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
    await db_session.commit()

    folder = await auth_client.post("/api/folders", json={"name": "Filing Target"})
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["id"]
    await auth_client.patch(
        f"/api/documents/{doc_id}/metadata",
        json={"folder_id": folder_id, "needs_review": False},
    )

    process = await auth_client.post(
        "/api/documents/process",
        json={"document_ids": [doc_id]},
    )
    assert process.status_code == 200, process.text
    result = process.json()
    assert len(result["processed"]) == 1
    assert result["processed"][0]["id"] == doc_id

    detail = await auth_client.get(f"/api/documents/{doc_id}")
    assert detail.json()["inbox"] is False
    assert detail.json()["inbox_status"] is None

    jobs = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == uuid.UUID(doc_id),
                Job.job_type == JobType.INDEXING,
            )
        )
    ).scalars().all()
    assert len(jobs) >= 1


@pytest.mark.asyncio
async def test_process_with_pending_folder_path(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
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
    await db_session.commit()

    await auth_client.patch(
        f"/api/documents/{doc_id}/metadata",
        json={"pending_folder_path": "Finance / Expenses", "needs_review": False},
    )

    process = await auth_client.post(
        "/api/documents/process",
        json={"document_ids": [doc_id]},
    )
    assert process.status_code == 200, process.text
    assert len(process.json()["processed"]) == 1

    detail = await auth_client.get(f"/api/documents/{doc_id}")
    body = detail.json()
    assert body["inbox"] is False
    assert body["pending_folder_path"] is None
    assert "Finance" in (body["folder_path"] or "")
    assert "Expenses" in (body["folder_path"] or "")


@pytest.mark.asyncio
async def test_tree_upload_pending_path_processes_into_library(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    """Folder upload stores pending path; Process materializes folders + INDEXING."""
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            data={"relative_path": "TreeImport/Nested/sample.txt", "on_duplicate": "skip"},
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    doc_id = body["id"]
    assert body["inbox"] is True
    assert body["pending_folder_path"] == "TreeImport/Nested"

    extract_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == uuid.UUID(doc_id),
                Job.job_type == JobType.TEXT_EXTRACTION,
            )
        )
    ).scalar_one()
    await process_text_extraction(db_session, extract_job)
    await db_session.commit()

    await auth_client.patch(
        f"/api/documents/{doc_id}/metadata",
        json={"needs_review": False},
    )

    process = await auth_client.post(
        "/api/documents/process",
        json={"document_ids": [doc_id]},
    )
    assert process.status_code == 200, process.text
    assert len(process.json()["processed"]) == 1

    detail = await auth_client.get(f"/api/documents/{doc_id}")
    final = detail.json()
    assert final["inbox"] is False
    assert final["pending_folder_path"] is None
    assert "TreeImport" in (final["folder_path"] or "")
    assert "Nested" in (final["folder_path"] or "")

    jobs = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == uuid.UUID(doc_id),
                Job.job_type == JobType.INDEXING,
            )
        )
    ).scalars().all()
    assert len(jobs) >= 1


@pytest.mark.asyncio
async def test_process_pending_path_revives_trashed_folders(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    """Filing into a soft-deleted path must revive folders, not 500 on unique name."""
    parent = await auth_client.post("/api/folders", json={"name": "Books"})
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]
    child = await auth_client.post(
        "/api/folders",
        json={"name": "Self-Help", "parent_id": parent_id},
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]

    trashed = await auth_client.post(f"/api/folders/{parent_id}/trash")
    assert trashed.status_code == 200, trashed.text

    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
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
    await db_session.commit()

    await auth_client.patch(
        f"/api/documents/{doc_id}/metadata",
        json={"pending_folder_path": "Books / Self-Help", "needs_review": False},
    )

    process = await auth_client.post(
        "/api/documents/process",
        json={"document_ids": [doc_id]},
    )
    assert process.status_code == 200, process.text
    result = process.json()
    assert len(result["processed"]) == 1, result
    assert result["failed"] == []

    detail = await auth_client.get(f"/api/documents/{doc_id}")
    body = detail.json()
    assert body["inbox"] is False
    assert body["folder_id"] == child_id
    assert "Books" in (body["folder_path"] or "")
    assert "Self-Help" in (body["folder_path"] or "")

    restored_parent = await auth_client.get(f"/api/folders/{parent_id}")
    assert restored_parent.status_code == 200
    assert restored_parent.json()["is_trashed"] is False


@pytest.mark.asyncio
async def test_remove_from_queue_deletes_document(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    doc_id = response.json()["id"]

    removed = await auth_client.post(f"/api/documents/{doc_id}/remove-from-queue")
    assert removed.status_code == 200, removed.text

    get_resp = await auth_client.get(f"/api/documents/{doc_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_folder_assign_preserves_inbox(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    doc_id = response.json()["id"]

    folder = await auth_client.post("/api/folders", json={"name": "Keep Inbox"})
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["id"]

    updated = await auth_client.patch(
        f"/api/documents/{doc_id}/metadata",
        json={"folder_id": folder_id},
    )
    assert updated.status_code == 200
    assert updated.json()["inbox"] is True
    assert updated.json()["folder_id"] == folder_id


@pytest.mark.asyncio
async def test_duplicate_still_upload_time_only(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        first = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert first.status_code == 201

    with sample_txt_path.open("rb") as fh:
        second = await auth_client.post(
            "/api/documents/upload",
            data={"on_duplicate": "skip"},
            files={"file": ("sample-copy.txt", fh, "text/plain")},
        )
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"

    inbox = await auth_client.get("/api/documents", params={"inbox": True})
    assert inbox.status_code == 200
    assert inbox.json()["total"] == 1
