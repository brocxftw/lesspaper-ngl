"""Unit tests for AI/OCR capability health derivation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lesspaper_ngl.ai.assignments import ResolvedAssignment
from lesspaper_ngl.ai.health import (
    HEALTH_PROBE_INTERVAL_SECONDS,
    derive_ocr_capability,
    derive_role_capability,
    probe_assigned_providers,
)
from lesspaper_ngl.models import AIWorkloadRole
from lesspaper_ngl.workers.processor import _provider_reachable_for_jobs


def _resolved(
    *,
    provider: object | None = None,
    model: str | None = "gpt-test",
) -> ResolvedAssignment:
    return ResolvedAssignment(
        role=AIWorkloadRole.INDEXING,
        provider=provider,  # type: ignore[arg-type]
        model=model,
        assignment=None,
    )


def _provider(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "name": "local-llm",
        "enabled": True,
        "last_probe_status": None,
        "last_probe_error": None,
        "last_probe_latency_ms": None,
        "last_probed_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_role_not_configured_without_provider() -> None:
    cap = derive_role_capability(
        capability="indexing",
        resolved=_resolved(provider=None, model=None),
    )
    assert cap.status == "not_configured"
    assert cap.provider is None


def test_role_not_configured_without_model() -> None:
    cap = derive_role_capability(
        capability="chat",
        resolved=_resolved(provider=_provider(), model=None),
    )
    assert cap.status == "not_configured"


def test_role_unavailable_when_disabled() -> None:
    cap = derive_role_capability(
        capability="embedding",
        resolved=_resolved(provider=_provider(enabled=False)),
    )
    assert cap.status == "unavailable"
    assert cap.error == "Provider is disabled"


def test_role_checking_before_first_probe() -> None:
    cap = derive_role_capability(
        capability="indexing",
        resolved=_resolved(provider=_provider()),
    )
    assert cap.status == "checking"


def test_role_unavailable_when_probe_offline() -> None:
    probed = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    cap = derive_role_capability(
        capability="indexing",
        resolved=_resolved(
            provider=_provider(
                last_probe_status="offline",
                last_probe_error="connection refused",
                last_probe_latency_ms=12,
                last_probed_at=probed,
            )
        ),
    )
    assert cap.status == "unavailable"
    assert cap.error == "connection refused"
    assert cap.latency_ms == 12
    assert cap.last_checked == probed


def test_role_available_when_probe_ok() -> None:
    probed = datetime(2026, 8, 11, 12, 1, tzinfo=UTC)
    cap = derive_role_capability(
        capability="chat",
        resolved=_resolved(
            provider=_provider(
                last_probe_status="available",
                last_probe_latency_ms=40,
                last_probed_at=probed,
            ),
            model="chat-model",
        ),
    )
    assert cap.status == "available"
    assert cap.model == "chat-model"
    assert cap.provider == "local-llm"
    assert cap.error is None


def test_capability_independence_embedding_down_indexing_up() -> None:
    probed = datetime(2026, 8, 11, 12, 2, tzinfo=UTC)
    indexing = derive_role_capability(
        capability="indexing",
        resolved=_resolved(
            provider=_provider(
                name="llm-a",
                last_probe_status="available",
                last_probed_at=probed,
            )
        ),
    )
    embedding = derive_role_capability(
        capability="embedding",
        resolved=_resolved(
            provider=_provider(
                name="llm-b",
                last_probe_status="offline",
                last_probe_error="timeout",
                last_probed_at=probed,
            ),
            model="embed-model",
        ),
    )
    assert indexing.status == "available"
    assert embedding.status == "unavailable"


def test_ocr_not_configured_when_disabled() -> None:
    settings = MagicMock()
    settings.ocr_enabled = False
    settings.ocr_language = "eng"
    with patch("lesspaper_ngl.ai.health.get_settings", return_value=settings):
        cap = derive_ocr_capability()
    assert cap.status == "not_configured"
    assert cap.capability == "ocr"


def test_ocr_unavailable_when_paddle_missing() -> None:
    settings = MagicMock()
    settings.ocr_enabled = True
    settings.ocr_language = "eng"
    with (
        patch("lesspaper_ngl.ai.health.get_settings", return_value=settings),
        patch("lesspaper_ngl.ai.health.paddle_ocr_available", return_value=False),
        patch("lesspaper_ngl.ai.health.get_paddle_import_error", return_value="no paddle"),
    ):
        cap = derive_ocr_capability()
    assert cap.status == "unavailable"
    assert "paddle" in (cap.error or "").lower()


def test_ocr_available_when_enabled_and_importable() -> None:
    settings = MagicMock()
    settings.ocr_enabled = True
    settings.ocr_language = "eng"
    with (
        patch("lesspaper_ngl.ai.health.get_settings", return_value=settings),
        patch("lesspaper_ngl.ai.health.paddle_ocr_available", return_value=True),
    ):
        cap = derive_ocr_capability()
    assert cap.status == "available"
    assert cap.provider == "paddleocr"


@pytest.mark.parametrize(
    ("enabled", "probe", "expected"),
    [
        (True, "available", True),
        (True, "offline", False),
        (True, None, False),
        (False, "available", False),
    ],
)
def test_provider_reachable_for_jobs(
    enabled: bool,
    probe: str | None,
    expected: bool,
) -> None:
    assert (
        _provider_reachable_for_jobs(
            _provider(enabled=enabled, last_probe_status=probe)
        )
        is expected
    )


def test_health_probe_interval_matches_documented_cadence() -> None:
    assert HEALTH_PROBE_INTERVAL_SECONDS == 10.0


@pytest.mark.asyncio
async def test_probe_assigned_providers_releases_session_before_http() -> None:
    import asyncio
    import uuid
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    open_sessions = {"count": 0}
    provider_id = uuid.uuid4()
    provider = SimpleNamespace(
        id=provider_id,
        name="local-llm",
        enabled=True,
        last_probe_status=None,
        last_probe_error=None,
        last_probe_latency_ms=None,
        last_probed_at=None,
        last_success_at=None,
    )

    @asynccontextmanager
    async def fake_scope():
        open_sessions["count"] += 1
        session = MagicMock()

        async def get(_model, _id):
            return provider

        session.get = get
        session.expunge = MagicMock()
        try:
            yield session
        finally:
            open_sessions["count"] -= 1

    async def list_ids(_session):
        return [provider_id]

    async def slow_test_connection():
        await asyncio.sleep(0.02)
        assert open_sessions["count"] == 0
        return True

    adapter = MagicMock()
    adapter.test_connection = slow_test_connection
    adapter.aclose = AsyncMock()

    with (
        patch("lesspaper_ngl.ai.health.session_scope", fake_scope),
        patch("lesspaper_ngl.ai.health._list_assigned_provider_ids", list_ids),
        patch("lesspaper_ngl.ai.health.get_adapter", return_value=adapter),
        patch("lesspaper_ngl.ai.health.is_provider_busy", return_value=False),
    ):
        count = await probe_assigned_providers()

    assert count == 1
    assert provider.last_probe_status == "available"
