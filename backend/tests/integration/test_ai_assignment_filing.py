"""Assignment UX: embedding flag, indexing auto-tagging, suggestion enqueue."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import AIProvider, Job, JobStatus, JobType
from lesspaper_ngl.workers.processor import process_text_extraction


async def _assign_local_indexing(auth_client: AsyncClient, db_session: AsyncSession) -> str:
    provider = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "filing-index-provider",
            "kind": "openai_compatible",
            "base_url": "http://127.0.0.1:9/v1",
            "is_local": True,
        },
    )
    assert provider.status_code == 201, provider.text
    provider_id = provider.json()["id"]

    assigned = await auth_client.patch(
        "/api/ai/assignments",
        json={"role": "indexing", "provider_id": provider_id, "model": "gemma"},
    )
    assert assigned.status_code == 200, assigned.text

    row = await db_session.get(AIProvider, uuid.UUID(provider_id))
    assert row is not None
    row.last_probe_status = "available"
    await db_session.commit()
    return provider_id


async def _upload_and_extract(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> uuid.UUID:
    response = await auth_client.post(
        "/api/documents/upload",
        files={
            "file": (
                "loan-summary.txt",
                b"LPPSA refinance summary for RM 420000 over 25 years.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201, response.text
    doc_id = uuid.UUID(response.json()["id"])
    extract_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.TEXT_EXTRACTION,
            )
        )
    ).scalar_one()
    extract_job.status = JobStatus.RUNNING
    await process_text_extraction(db_session, extract_job)
    extract_job.status = JobStatus.COMPLETED
    await db_session.commit()
    return doc_id


async def _suggestion_job(db_session: AsyncSession, doc_id: uuid.UUID) -> Job | None:
    return (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.METADATA_SUGGESTION,
            )
        )
    ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_extraction_enqueues_suggestions_after_indexing_assignment(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _assign_local_indexing(auth_client, db_session)
    policy = await auth_client.get("/api/ai/policy")
    assert policy.json()["auto_tagging"] is True

    doc_id = await _upload_and_extract(auth_client, db_session)
    assert await _suggestion_job(db_session, doc_id) is not None


@pytest.mark.asyncio
async def test_extraction_skips_suggestions_when_auto_tagging_off(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _assign_local_indexing(auth_client, db_session)
    disabled = await auth_client.patch("/api/ai/policy", json={"auto_tagging": False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["auto_tagging"] is False

    doc_id = await _upload_and_extract(auth_client, db_session)
    assert await _suggestion_job(db_session, doc_id) is None
