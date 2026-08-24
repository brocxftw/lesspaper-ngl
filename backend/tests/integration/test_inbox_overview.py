"""Inbox overview metrics and activity API tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import Job, JobType
from lesspaper_ngl.workers.processor import process_text_extraction


@pytest.mark.asyncio
async def test_inbox_overview_and_activity_after_process(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("overview-sample.txt", fh, "text/plain")},
        )
    assert response.status_code == 201, response.text
    doc_id = response.json()["id"]

    # Fresh upload is still in the queue → processing/queued counts visible.
    overview_before = await auth_client.get("/api/inbox/overview", params={"range_days": 7})
    assert overview_before.status_code == 200, overview_before.text
    before = overview_before.json()
    assert before["total_ingested"] >= 1
    assert before["processing"] >= 1

    activity_before = await auth_client.get(
        "/api/inbox/activity",
        params={"range_days": 7, "tab": "recent"},
    )
    assert activity_before.status_code == 200, activity_before.text
    assert any(item["id"] == doc_id for item in activity_before.json()["items"])
    queued_or_processing = {
        item["activity_status"]
        for item in activity_before.json()["items"]
        if item["id"] == doc_id
    }
    assert queued_or_processing & {"queued", "processing"}

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

    folder = await auth_client.post("/api/folders", json={"name": "Overview Target"})
    assert folder.status_code == 201, folder.text
    await auth_client.patch(
        f"/api/documents/{doc_id}/metadata",
        json={"folder_id": folder.json()["id"], "needs_review": False},
    )

    process = await auth_client.post(
        "/api/documents/process",
        json={"document_ids": [doc_id]},
    )
    assert process.status_code == 200, process.text
    assert len(process.json()["processed"]) == 1

    overview_after = await auth_client.get("/api/inbox/overview", params={"range_days": 7})
    assert overview_after.status_code == 200, overview_after.text
    after = overview_after.json()
    assert after["processed"] >= 1
    assert after["total_ingested"] >= 1
    assert after["success_rate"] is not None

    activity_after = await auth_client.get(
        "/api/inbox/activity",
        params={"range_days": 7, "tab": "processed"},
    )
    assert activity_after.status_code == 200, activity_after.text
    match = next(item for item in activity_after.json()["items"] if item["id"] == doc_id)
    assert match["inbox"] is False
    assert match["activity_status"] == "processed"
