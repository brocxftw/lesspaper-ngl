"""Job requeue helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import (
    Document,
    Folder,
    FolderKind,
    Job,
    JobStatus,
    JobType,
    ProcessingStatus,
    User,
)
from lesspaper_ngl.services import jobs as job_service


async def _owner_and_folder(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user = User(
        username=f"jobs_{uuid.uuid4().hex[:8]}",
        password_hash="unused",
        display_name="Jobs",
    )
    db_session.add(user)
    await db_session.flush()
    folder = Folder(owner_id=user.id, name="Inbox", kind=FolderKind.INBOX, path_cache="Inbox")
    db_session.add(folder)
    await db_session.flush()
    return user.id, folder.id


@pytest.mark.asyncio
async def test_requeue_all_running(db_session: AsyncSession) -> None:
    running = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.RUNNING,
        locked_by="dead-worker-1",
        priority=50,
    )
    queued = Job(
        job_type=JobType.THUMBNAIL,
        status=JobStatus.QUEUED,
        priority=50,
    )
    db_session.add_all([running, queued])
    await db_session.flush()

    n = await job_service.requeue_all_running(db_session)
    assert n == 1
    await db_session.commit()

    rows = (await db_session.execute(select(Job))).scalars().all()
    by_type = {j.job_type: j for j in rows}
    assert by_type[JobType.TEXT_EXTRACTION].status == JobStatus.QUEUED
    assert by_type[JobType.TEXT_EXTRACTION].locked_by is None
    assert by_type[JobType.THUMBNAIL].status == JobStatus.QUEUED


@pytest.mark.asyncio
async def test_cancel_jobs_for_trashed_documents(db_session: AsyncSession) -> None:
    owner_id, folder_id = await _owner_and_folder(db_session)
    live = Document(
        owner_id=owner_id,
        title="live",
        original_filename="live.txt",
        storage_key="k-live",
        checksum=f"c-live-{uuid.uuid4().hex}",
        mime_type="text/plain",
        file_size=1,
        folder_id=folder_id,
        inbox=True,
        is_trashed=False,
    )
    trash = Document(
        owner_id=owner_id,
        title="trash",
        original_filename="seg01_t000.png",
        storage_key="k-trash",
        checksum=f"c-trash-{uuid.uuid4().hex}",
        mime_type="image/png",
        file_size=1,
        folder_id=folder_id,
        inbox=False,
        is_trashed=True,
    )
    db_session.add_all([live, trash])
    await db_session.flush()
    live_job = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.QUEUED,
        document_id=live.id,
        priority=50,
    )
    trash_job = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.QUEUED,
        document_id=trash.id,
        priority=10,
    )
    db_session.add_all([live_job, trash_job])
    await db_session.flush()

    n = await job_service.cancel_jobs_for_trashed_documents(db_session)
    assert n == 1
    await db_session.commit()

    claimed = await job_service.claim_next(db_session, "worker-test")
    assert claimed is not None
    assert claimed.document_id == live.id
    assert claimed.id == live_job.id


async def _inbox_doc(
    db_session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    folder_id: uuid.UUID,
    name: str,
    added: datetime,
) -> Document:
    doc = Document(
        owner_id=owner_id,
        title=name,
        original_filename=name,
        storage_key=f"k-{name}",
        checksum=f"c-{uuid.uuid4().hex}",
        mime_type="text/plain",
        file_size=1,
        folder_id=folder_id,
        inbox=True,
        added_date=added,
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


@pytest.mark.asyncio
async def test_claim_next_serializes_inbox_preflight(db_session: AsyncSession) -> None:
    owner_id, folder_id = await _owner_and_folder(db_session)
    now = datetime.now(UTC)
    older = await _inbox_doc(
        db_session, owner_id=owner_id, folder_id=folder_id, name="a.txt", added=now
    )
    newer = await _inbox_doc(
        db_session,
        owner_id=owner_id,
        folder_id=folder_id,
        name="b.txt",
        added=now + timedelta(seconds=1),
    )
    older_job = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.QUEUED,
        document_id=older.id,
        priority=50,
    )
    newer_job = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.QUEUED,
        document_id=newer.id,
        priority=50,
    )
    db_session.add_all([older_job, newer_job])
    await db_session.flush()

    first = await job_service.claim_next(db_session, "w1")
    assert first is not None
    assert first.document_id == older.id

    second = await job_service.claim_next(db_session, "w1")
    assert second is None

    first.status = JobStatus.COMPLETED
    first.locked_by = None
    await db_session.flush()

    third = await job_service.claim_next(db_session, "w1")
    assert third is not None
    assert third.document_id == newer.id


@pytest.mark.asyncio
async def test_claim_next_allows_same_doc_thumbnail(db_session: AsyncSession) -> None:
    owner_id, folder_id = await _owner_and_folder(db_session)
    now = datetime.now(UTC)
    older = await _inbox_doc(
        db_session, owner_id=owner_id, folder_id=folder_id, name="a.txt", added=now
    )
    newer = await _inbox_doc(
        db_session,
        owner_id=owner_id,
        folder_id=folder_id,
        name="b.txt",
        added=now + timedelta(seconds=1),
    )
    extract = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.QUEUED,
        document_id=older.id,
        priority=50,
    )
    thumb = Job(
        job_type=JobType.THUMBNAIL,
        status=JobStatus.QUEUED,
        document_id=older.id,
        priority=60,
    )
    other = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.QUEUED,
        document_id=newer.id,
        priority=50,
    )
    db_session.add_all([extract, thumb, other])
    await db_session.flush()

    first = await job_service.claim_next(db_session, "w1")
    assert first is not None
    assert first.id == extract.id

    second = await job_service.claim_next(db_session, "w1")
    assert second is not None
    assert second.id == thumb.id


@pytest.mark.asyncio
async def test_claim_next_allows_library_jobs_during_inbox_preflight(
    db_session: AsyncSession,
) -> None:
    owner_id, folder_id = await _owner_and_folder(db_session)
    now = datetime.now(UTC)
    inbox_doc = await _inbox_doc(
        db_session, owner_id=owner_id, folder_id=folder_id, name="a.txt", added=now
    )
    library = Document(
        owner_id=owner_id,
        title="lib",
        original_filename="lib.txt",
        storage_key="k-lib",
        checksum=f"c-{uuid.uuid4().hex}",
        mime_type="text/plain",
        file_size=1,
        folder_id=folder_id,
        inbox=False,
    )
    db_session.add(library)
    await db_session.flush()
    extract = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.QUEUED,
        document_id=inbox_doc.id,
        priority=50,
    )
    db_session.add(extract)
    await db_session.flush()

    first = await job_service.claim_next(db_session, "w1")
    assert first is not None
    assert first.id == extract.id

    indexing = Job(
        job_type=JobType.INDEXING,
        status=JobStatus.QUEUED,
        document_id=library.id,
        priority=50,
    )
    db_session.add(indexing)
    await db_session.flush()

    second = await job_service.claim_next(db_session, "w1")
    assert second is not None
    assert second.id == indexing.id


@pytest.mark.asyncio
async def test_claim_next_allows_ready_inbox_suggestion_during_other_extract(
    db_session: AsyncSession,
) -> None:
    owner_id, folder_id = await _owner_and_folder(db_session)
    now = datetime.now(UTC)
    preparing = await _inbox_doc(
        db_session, owner_id=owner_id, folder_id=folder_id, name="a.txt", added=now
    )
    ready = await _inbox_doc(
        db_session,
        owner_id=owner_id,
        folder_id=folder_id,
        name="b.txt",
        added=now + timedelta(seconds=1),
    )
    ready.processing_status = ProcessingStatus.READY
    extract = Job(
        job_type=JobType.TEXT_EXTRACTION,
        status=JobStatus.QUEUED,
        document_id=preparing.id,
        priority=50,
    )
    db_session.add(extract)
    await db_session.flush()

    first = await job_service.claim_next(db_session, "w1")
    assert first is not None
    assert first.id == extract.id

    suggestion = Job(
        job_type=JobType.METADATA_SUGGESTION,
        status=JobStatus.QUEUED,
        document_id=ready.id,
        priority=70,
    )
    db_session.add(suggestion)
    await db_session.flush()

    second = await job_service.claim_next(db_session, "w1")
    assert second is not None
    assert second.id == suggestion.id
