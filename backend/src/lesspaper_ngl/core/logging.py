"""Structured logging helpers."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import sys
import traceback
from contextlib import suppress
from typing import Any

from lesspaper_ngl.core.config import get_settings

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
_log_queue: asyncio.Queue[dict[str, Any]] | None = None
_log_consumer: asyncio.Task[None] | None = None
_log_loop: asyncio.AbstractEventLoop | None = None


async def _consume_database_logs(queue: asyncio.Queue[dict[str, Any]]) -> None:
    from lesspaper_ngl.services.application_logs import persist_event

    while True:
        event = await queue.get()
        try:
            # The original event has already reached stdout. Database
            # persistence must never terminate the bounded consumer.
            with suppress(Exception):
                await persist_event(**event)
        finally:
            queue.task_done()


def _queue_for_loop() -> asyncio.Queue[dict[str, Any]]:
    global _log_consumer, _log_loop, _log_queue
    loop = asyncio.get_running_loop()
    if _log_queue is None or _log_loop is not loop:
        _log_queue = asyncio.Queue(maxsize=1000)
        _log_consumer = None
        _log_loop = loop
    if _log_consumer is None or _log_consumer.done():
        _log_consumer = asyncio.create_task(_consume_database_logs(_log_queue))
    return _log_queue


class DatabaseLogHandler(logging.Handler):
    def __init__(self, service: str) -> None:
        super().__init__(level=logging.INFO)
        self.service = service

    def emit(self, record: logging.LogRecord) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        context = {
            key: getattr(record, key)
            for key in (
                "document_id",
                "provider",
                "model",
                "duration_ms",
                "method",
                "path",
                "status_code",
                "job_id",
                "job_type",
            )
            if hasattr(record, key)
        }
        stack = None
        if record.exc_info:
            stack = "".join(traceback.format_exception(*record.exc_info))
        event = {
            "level": record.levelname,
            "service": self.service,
            "module": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
            "context": context,
            "stack_trace": stack,
        }
        try:
            _queue_for_loop().put_nowait(event)
        except asyncio.QueueFull:
            # stdout remains the source of truth while the bounded store queue
            # is saturated; application work must not block on log persistence.
            return


def setup_logging(service: str = "api") -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger().addHandler(DatabaseLogHandler(service))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
