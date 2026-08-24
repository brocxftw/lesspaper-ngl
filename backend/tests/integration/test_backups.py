"""Backup API and round-trip integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.backup.dump import pg_tools_available
from lesspaper_ngl.backup.restore import execute_restore
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.db.session import dispose_engine, get_session_factory
from lesspaper_ngl.models import Document, InstanceState, Job, JobStatus, JobType, User
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.services.jobs import complete_job
from lesspaper_ngl.workers.processor import process_job

pytestmark = pytest.mark.asyncio

_PG = pg_tools_available()


async def _run_backup_jobs(session: AsyncSession) -> None:
    jobs = (
        await session.execute(
            select(Job).where(
                Job.job_type.in_([JobType.BACKUP, JobType.BACKUP_VERIFY]),
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
    ).scalars().all()
    for job in jobs:
        result = await process_job(session, job)
        await complete_job(session, job.id, result)
    await session.commit()


async def test_backup_settings_admin_only(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/backups/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["retention_count"] == 7
    assert body["verify_after_backup"] is True
    assert "repository" in body


async def test_backup_settings_validation(auth_client: AsyncClient) -> None:
    response = await auth_client.patch("/api/backups/settings", json={"retention_count": 0})
    assert response.status_code == 422


async def test_backup_settings_enable_schedule(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(
        "/api/backups/settings",
        json={"enabled": True, "schedule_type": "daily", "backup_time": "03:30"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    assert body["next_run_at"] is not None


async def test_unauthenticated_backup_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/backups/settings")
    assert response.status_code == 401


async def test_health_includes_instance_state(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["instance_state"] == "ready"


async def test_bootstrap_status_ready_after_test_setup(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/bootstrap/status")
    assert response.status_code == 200
    assert response.json()["ready"] is True
    denied = await auth_client.post("/api/bootstrap/setup")
    assert denied.status_code == 403


async def test_bootstrap_setup_from_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    from sqlalchemy import text

    await db_session.execute(text("TRUNCATE TABLE sessions, users CASCADE"))
    await instance_state_service.set_instance_state(db_session, InstanceState.UNINITIALISED)
    await db_session.commit()

    status = await client.get("/api/bootstrap/status")
    assert status.status_code == 200
    assert status.json()["instance_state"] == "uninitialised"
    assert status.json()["ready"] is False

    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["instance_state"] == "uninitialised"

    register = await client.post(
        "/api/auth/register",
        json={"username": "newbie", "password": "testpass123", "display_name": "New"},
    )
    assert register.status_code == 401

    setup = await client.post("/api/bootstrap/setup")
    assert setup.status_code == 200, setup.text
    assert setup.json()["ready"] is True


async def test_missing_backup_repository_fails_cleanly(
    auth_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    restore_storage_paths: None,
) -> None:
    del restore_storage_paths
    missing = tmp_path / "no-such-backups"
    monkeypatch.setenv("BACKUPS_PATH", str(missing))
    get_settings.cache_clear()
    response = await auth_client.post("/api/backups")
    assert response.status_code == 503
    get_settings.cache_clear()


async def test_manual_backup_round_trip(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path: Path,
) -> None:
    if not _PG:
        pytest.skip("PostgreSQL 17 client (pg_dump) is not available")

    with sample_txt_path.open("rb") as fh:
        upload = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert upload.status_code == 201, upload.text

    queued = await auth_client.post("/api/backups")
    assert queued.status_code == 202, queued.text
    await _run_backup_jobs(db_session)

    listed = await auth_client.get("/api/backups")
    assert listed.status_code == 200
    completed = [item for item in listed.json() if item["status"] == "completed"]
    assert completed, listed.json()
    backup_id = completed[0]["id"]
    filename = completed[0]["filename"]

    inspect = await auth_client.get(f"/api/backups/{backup_id}/inspect")
    assert inspect.status_code == 200
    assert inspect.json()["compatible"] is True

    verify = await auth_client.post(f"/api/backups/{backup_id}/verify")
    assert verify.status_code == 200
    await _run_backup_jobs(db_session)
    listed = await auth_client.get("/api/backups")
    verified = next(item for item in listed.json() if item["id"] == backup_id)
    assert verified["verification_status"] in {"healthy", "unverified"}

    await db_session.commit()
    await execute_restore(filename, safety_dump=False)
    await dispose_engine()
    factory = get_session_factory()
    async with factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        docs = (await session.execute(select(Document).where(Document.is_trashed.is_(False)))).scalars().all()
        assert users
        assert docs
        assert await instance_state_service.get_instance_state(session) == InstanceState.READY
        original = get_settings().originals_path / docs[0].storage_key
        assert original.is_file()

    delete = await auth_client.delete(f"/api/backups/{backup_id}", json={"confirm": True})
    assert delete.status_code == 204


async def test_missing_original_fails_backup(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path: Path,
) -> None:
    if not _PG:
        pytest.skip("PostgreSQL 17 client (pg_dump) is not available")

    with sample_txt_path.open("rb") as fh:
        upload = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert upload.status_code == 201, upload.text
    doc = (await db_session.execute(select(Document))).scalar_one()
    path = get_settings().originals_path / doc.storage_key
    path.unlink()

    queued = await auth_client.post("/api/backups")
    assert queued.status_code == 202, queued.text
    with pytest.raises(RuntimeError, match="Missing"):
        await _run_backup_jobs(db_session)

    listed = await auth_client.get("/api/backups")
    failed = [item for item in listed.json() if item["status"] == "failed"]
    assert failed
    assert not list(get_settings().backups_path.glob("*.folium"))
