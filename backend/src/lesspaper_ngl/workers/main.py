"""lesspaper-ngl background worker entrypoint."""

from __future__ import annotations

import asyncio
import os
import socket
from contextlib import suppress
from datetime import UTC, datetime

from lesspaper_ngl.ai.health import HEALTH_PROBE_INTERVAL_SECONDS, probe_assigned_providers
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.logging import get_logger, setup_logging
from lesspaper_ngl.db.session import session_scope
from lesspaper_ngl.models import AppSetting, InstanceState
from lesspaper_ngl.services import backup as backup_service
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.services import jobs as job_service
from lesspaper_ngl.storage.service import StorageService
from lesspaper_ngl.workers.healthcheck import WORKER_HEARTBEAT_KEY
from lesspaper_ngl.workers.ocr_gate import ocr_exclusive_locked
from lesspaper_ngl.workers.processor import process_consume_file, process_job

logger = get_logger(__name__)


def worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def _instance_is_ready() -> bool:
    async with session_scope() as session:
        state = await instance_state_service.get_instance_state(session)
        return state == InstanceState.READY


async def _poll_jobs(wid: str, sem: asyncio.Semaphore) -> None:
    if not await _instance_is_ready():
        return
    settings = get_settings()
    async with session_scope() as session:
        await job_service.requeue_stale_running(
            session, older_than_seconds=settings.job_stale_running_seconds
        )

    # While OCR holds the exclusive gate, do not claim more work (even if
    # JOB_CONCURRENCY > 1) so indexing/backup peaks do not stack on OCR RAM.
    if ocr_exclusive_locked():
        return

    # Acquire capacity BEFORE claiming so jobs are not marked running while waiting.
    # Do not use wait_for(acquire, timeout=0): it can take a permit then cancel,
    # permanently leaking concurrency slots.
    if sem.locked():
        return

    await sem.acquire()
    try:
        async with session_scope() as session:
            job = await job_service.claim_next(session, wid)
    except Exception:
        sem.release()
        raise

    if job is None:
        sem.release()
        return

    async def _run() -> None:
        stop_heartbeat = asyncio.Event()

        async def _lock_heartbeat() -> None:
            interval = max(settings.job_lock_heartbeat_seconds, 5.0)
            while not stop_heartbeat.is_set():
                try:
                    await asyncio.wait_for(stop_heartbeat.wait(), timeout=interval)
                    return
                except TimeoutError:
                    try:
                        async with session_scope() as session:
                            await job_service.touch_job_lock(session, job.id)
                    except Exception:
                        logger.debug("Job lock heartbeat failed for %s", job.id, exc_info=True)

        heartbeat_task = asyncio.create_task(_lock_heartbeat())
        try:
            try:
                async with session_scope() as session:
                    fresh = await job_service.get_job(session, job.id)
                    result = await process_job(session, fresh)
                    await job_service.complete_job(session, fresh.id, result)
                logger.info("Completed job %s (%s)", job.id, job.job_type.value)
            except Exception as exc:
                logger.exception("Job %s failed: %s", job.id, exc)
                async with session_scope() as session:
                    from lesspaper_ngl.ai.base import AIProviderError
                    from lesspaper_ngl.ai.retry import (
                        is_transient_ai_error,
                        job_retry_delay_seconds,
                    )
                    from lesspaper_ngl.models import JobStatus
                    from lesspaper_ngl.workers.processor import (
                        PREFLIGHT_JOB_TYPES,
                        SOFT_FAIL_PREFLIGHT_JOB_TYPES,
                        mark_preflight_failed,
                        mark_preflight_ready,
                    )

                    delay: float | None = None
                    if isinstance(exc, AIProviderError) and is_transient_ai_error(exc):
                        # retry_count is incremented inside fail_job; peek current value.
                        current = await job_service.get_job(session, job.id)
                        delay = job_retry_delay_seconds(current.retry_count + 1)

                    failed = await job_service.fail_job(
                        session, job.id, str(exc), delay_seconds=delay
                    )

                    if (
                        failed.status == JobStatus.FAILED
                        and failed.document_id is not None
                        and failed.job_type in PREFLIGHT_JOB_TYPES
                    ):
                        if failed.job_type in SOFT_FAIL_PREFLIGHT_JOB_TYPES:
                            # AI enrichment is optional — degrade to manual review.
                            logger.warning(
                                "AI preflight soft-failed for doc=%s (%s): %s",
                                failed.document_id,
                                failed.job_type.value,
                                exc,
                            )
                            await mark_preflight_ready(session, failed.document_id)
                        else:
                            await mark_preflight_failed(session, failed.document_id, str(exc))

                    if (
                        failed.status == JobStatus.FAILED
                        and failed.document_id is not None
                        and failed.job_type.value == "embedding"
                    ):
                        from lesspaper_ngl.models import Document

                        doc = await session.get(Document, failed.document_id)
                        if doc is not None:
                            # Keep completed vectors; surface actionable status.
                            msg = str(exc)
                            if len(msg) > 400:
                                msg = msg[:397] + "..."
                            doc.embedding_error = msg or "Embedding provider unavailable"
                            if doc.chunks_embedded and doc.chunks_embedded > 0:
                                from lesspaper_ngl.models import ProcessingStatus

                                doc.processing_status = ProcessingStatus.PARTIAL
                                doc.has_embeddings = True

                    # SUMMARY is post-Process; terminal AI failure must not alter filing.
                    if (
                        failed.status == JobStatus.FAILED
                        and failed.job_type.value == "summary"
                    ):
                        logger.warning(
                            "SUMMARY soft-failed for doc=%s: %s",
                            failed.document_id,
                            exc,
                        )
        finally:
            stop_heartbeat.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            sem.release()

    asyncio.create_task(_run())


async def _poll_consume(stability_wait: float) -> None:
    if not await _instance_is_ready():
        return
    storage = StorageService()
    files = storage.list_consume_files()
    if not files:
        return

    await asyncio.sleep(stability_wait)

    for path in files:
        if not path.is_file():
            continue
        if not storage.is_file_stable(path):
            continue
        try:
            async with session_scope() as session:
                doc_id = await process_consume_file(session, path, storage=storage)
            if doc_id:
                logger.info("Consumed file -> document %s", doc_id)
        except Exception as exc:
            logger.exception("Failed to consume file: %s", exc)


async def _poll_trash_purge(last_run: list[float]) -> None:
    """Periodically purge trash older than the retention window."""
    if not await _instance_is_ready():
        return
    import time as time_mod

    settings = get_settings()
    now = time_mod.monotonic()
    if last_run[0] and now - last_run[0] < settings.trash_purge_interval_seconds:
        return
    last_run[0] = now
    try:
        from lesspaper_ngl.services import documents as doc_service

        async with session_scope() as session:
            result = await doc_service.purge_expired_trash(
                session,
                owner_id=None,
                storage=StorageService(),
            )
        if result["deleted_documents"] or result["deleted_folders"]:
            logger.info(
                "Purged trash: %s document(s), %s folder(s) (retention=%sd)",
                result["deleted_documents"],
                result["deleted_folders"],
                result["retention_days"],
            )
    except Exception as exc:
        logger.exception("Trash purge failed: %s", exc)


async def _poll_backup_schedule(last_run: list[float]) -> None:
    import time as time_mod

    if not await _instance_is_ready():
        return
    now_mono = time_mod.monotonic()
    if last_run[0] and now_mono - last_run[0] < 30.0:
        return
    last_run[0] = now_mono
    try:
        from lesspaper_ngl.backup.schedule import next_run_after

        async with session_scope() as session:
            policy = await backup_service.get_or_create_settings(session)
            if not policy.enabled or policy.next_run_at is None:
                return
            now = datetime.now(UTC)
            if now < policy.next_run_at:
                return
            if await backup_service.has_active_backup_job(session):
                policy.next_run_at = next_run_after(policy, now)
                return
            await backup_service.create_backup_record(session, manual=False)
            policy.next_run_at = next_run_after(policy, now)
    except Exception as exc:
        logger.exception("Backup schedule failed: %s", exc)


async def _poll_ai_health(last_run: list[float], in_flight: list[asyncio.Task | None]) -> None:
    """Schedule a non-blocking health probe every HEALTH_PROBE_INTERVAL_SECONDS.

    Must not be awaited inside the job-poll gather — a down provider used to
    stall OCR/extract claiming for minutes (adapter 120s × retries).
    """
    import time as time_mod

    task = in_flight[0]
    if task is not None and not task.done():
        return

    now = time_mod.monotonic()
    if last_run[0] and now - last_run[0] < HEALTH_PROBE_INTERVAL_SECONDS:
        return
    last_run[0] = now

    async def _run() -> None:
        try:
            count = await probe_assigned_providers()
            if count:
                logger.debug("AI health probe completed for %s provider(s)", count)
        except Exception as exc:
            logger.exception("AI health probe failed: %s", exc)

    in_flight[0] = asyncio.create_task(_run())


WORKER_LIVENESS_INTERVAL_SECONDS = 10.0


async def _write_worker_heartbeat(wid: str) -> None:
    async with session_scope() as session:
        heartbeat = await session.get(AppSetting, WORKER_HEARTBEAT_KEY)
        value = {"at": datetime.now(UTC).isoformat(), "worker_id": wid}
        if heartbeat is None:
            session.add(AppSetting(key=WORKER_HEARTBEAT_KEY, value=value))
        else:
            heartbeat.value = value


async def _liveness_heartbeat(wid: str, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await _write_worker_heartbeat(wid)
        except Exception:
            logger.debug("Worker liveness heartbeat failed", exc_info=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=WORKER_LIVENESS_INTERVAL_SECONDS)
        except TimeoutError:
            continue


async def worker_loop() -> None:
    settings = get_settings()
    wid = worker_id()
    sem = asyncio.Semaphore(settings.job_concurrency)
    last_purge: list[float] = [0.0]
    last_backup: list[float] = [0.0]
    last_ai_health: list[float] = [0.0]
    ai_health_task: list[asyncio.Task | None] = [None]
    logger.info("Worker %s started (concurrency=%s)", wid, settings.job_concurrency)

    # Abandoned RUNNING jobs from a previous container must not block the queue.
    # Trashed-document jobs must not starve active Inbox/library work.
    async with session_scope() as session:
        recovered = await job_service.requeue_all_running(session)
        cancelled_trashed = await job_service.cancel_jobs_for_trashed_documents(session)
    if recovered:
        logger.info("Requeued %s abandoned running job(s) on startup", recovered)
    if cancelled_trashed:
        logger.info(
            "Cancelled %s job(s) for trashed documents on startup", cancelled_trashed
        )
    backup_service.startup_cleanup()

    stop_liveness = asyncio.Event()
    liveness_task = asyncio.create_task(_liveness_heartbeat(wid, stop_liveness))
    try:
        while True:
            # Health probe is fire-and-forget so unreachable AI cannot block jobs.
            await _poll_ai_health(last_ai_health, ai_health_task)
            tasks = [
                _poll_jobs(wid, sem),
                _poll_consume(settings.consume_poll_interval_seconds),
                _poll_trash_purge(last_purge),
                _poll_backup_schedule(last_backup),
            ]
            await asyncio.gather(*tasks)
            await asyncio.sleep(settings.job_poll_interval_seconds)
    finally:
        stop_liveness.set()
        liveness_task.cancel()
        with suppress(asyncio.CancelledError):
            await liveness_task


def run_worker() -> None:
    setup_logging("worker")
    storage = StorageService()
    storage.ensure_layout()
    asyncio.run(worker_loop())


if __name__ == "__main__":
    run_worker()
