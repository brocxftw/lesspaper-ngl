"""Privacy mode integration tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import AIProvider, Job, JobType
from lesspaper_ngl.workers.processor import process_embedding


async def _configure_remote_providers(
    auth_client: AsyncClient,
    db_session: AsyncSession | None = None,
) -> tuple[str, str]:
    chat = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "remote-chat",
            "kind": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "is_local": False,
            "chat_model": "gpt-test",
            "supports_embeddings": False,
        },
    )
    assert chat.status_code == 201
    chat_id = chat.json()["id"]

    embed = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "remote-embed",
            "kind": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "is_local": False,
            "embedding_model": "embed-test",
            "supports_embeddings": True,
        },
    )
    assert embed.status_code == 201
    embed_id = embed.json()["id"]

    # Reach PrivacyGate (not the soft-skip probe gate) for embedding jobs.
    if db_session is not None:
        for provider_id in (chat_id, embed_id):
            row = await db_session.get(AIProvider, uuid.UUID(provider_id))
            assert row is not None
            row.last_probe_status = "available"
        await db_session.commit()

    policy = await auth_client.patch(
        "/api/ai/policy",
        json={
            "privacy_mode": "local_only",
            "chat_provider_id": chat_id,
            "embedding_provider_id": embed_id,
        },
    )
    assert policy.status_code == 200
    assert policy.json()["privacy_mode"] == "local_only"
    return chat_id, embed_id


@pytest.mark.asyncio
async def test_local_only_blocks_remote_qa(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
) -> None:
    await _configure_remote_providers(auth_client)

    response = await auth_client.post(
        f"/api/documents/{uploaded_txt_doc['id']}/ask",
        json={"question": "What is the loan amount?", "confirm_remote": True},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "privacy_violation"


@pytest.mark.asyncio
async def test_local_only_blocks_remote_embeddings(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
    db_session: AsyncSession,
) -> None:
    await _configure_remote_providers(auth_client, db_session)

    from sqlalchemy import select

    job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == uuid.UUID(uploaded_txt_doc["id"]),
                Job.job_type == JobType.EMBEDDING,
            )
        )
    ).scalar_one_or_none()

    if job is None:
        from lesspaper_ngl.services.jobs import enqueue_job

        job = await enqueue_job(
            db_session,
            job_type=JobType.EMBEDDING,
            document_id=uuid.UUID(uploaded_txt_doc["id"]),
        )
        await db_session.commit()

    with pytest.raises(Exception) as exc_info:
        await process_embedding(db_session, job)
    assert "privacy" in str(exc_info.value).lower() or exc_info.value.__class__.__name__ == "PrivacyViolationError"
