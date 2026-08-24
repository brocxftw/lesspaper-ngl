"""End-to-end AI filing suggestion pipeline (folder + tags) with printable report.

Run with::

    cd backend && uv run pytest tests/integration/test_ai_filing_pipeline.py -s -v

The ``-s`` flag keeps the step-by-step report visible so you can verify each
stage: extract → suggest → accept folder/tags → process.

For a live LM Studio run (real model)::

    FOLIUM_LIVE_AI=1 uv run pytest tests/integration/test_ai_filing_pipeline.py -s -k live
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.base import (
    AIProviderAdapter,
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ModelCapabilities,
)
from lesspaper_ngl.models import AIProvider, AISuggestion, Job, JobStatus, JobType, SuggestionStatus
from lesspaper_ngl.workers.processor import process_metadata_suggestion, process_text_extraction

# ---------------------------------------------------------------------------
# Visual report helpers (visible with pytest -s)
# ---------------------------------------------------------------------------


def _banner(title: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n  {title}\n{line}")


def _step(n: int, label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"  [{n:02d}] {label}{suffix}")


def _kv(key: str, value: Any) -> None:
    print(f"       {key}: {value}")


def _print_suggestions(rows: list[dict]) -> None:
    if not rows:
        print("       (no suggestions)")
        return
    for s in rows:
        field = s.get("field")
        value = s.get("value")
        status = s.get("status")
        print(f"       • {field:16} status={status}")
        print(f"         value={json.dumps(value, ensure_ascii=False)}")


# ---------------------------------------------------------------------------
# Mock chat adapter
# ---------------------------------------------------------------------------

_MOCK_PAYLOAD = {
    "folder_path": "Finance / Insurance",
    "create_folder": True,
    "title": "LPPSA Refinance Summary",
    "document_type": None,
    "correspondent": None,
    "tags": [
        {"name": "lppsa", "confidence": 0.92},
        {"name": "refinance", "confidence": 0.88},
        {"name": "housing-loan", "confidence": 0.81},
    ],
    "confidence": {
        "folder": 0.94,
        "title": 0.9,
    },
    "needs_review": False,
}


@dataclass
class _MockFilingAdapter(AIProviderAdapter):
    """Returns deterministic folder + tag suggestions."""

    payload: dict = field(default_factory=lambda: dict(_MOCK_PAYLOAD))
    wrap_in_fence: bool = False
    last_prompt: str | None = None
    provider_name: str = "mock-filing"
    is_local: bool = True

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(supports_chat=True)

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        del max_tokens, temperature
        self.last_prompt = messages[-1].content if messages else None
        body = json.dumps(self.payload)
        content = f"```json\n{body}\n```" if self.wrap_in_fence else body
        return ChatResult(
            content=content,
            model=model or "mock-filing",
            input_tokens=120,
            output_tokens=40,
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        del texts
        return EmbeddingResult(embeddings=[], model=model or "mock")

    async def test_connection(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


async def _enable_auto_tagging(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> str:
    provider = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "mock-filing-chat",
            "kind": "ollama",
            "base_url": "http://localhost:11434",
            "is_local": True,
            "chat_model": "mock-filing",
        },
    )
    assert provider.status_code == 201, provider.text
    provider_id = provider.json()["id"]

    # Metadata suggestion enqueue requires a recent successful health probe.
    row = await db_session.get(AIProvider, uuid.UUID(provider_id))
    assert row is not None
    row.last_probe_status = "available"
    await db_session.commit()

    policy = await auth_client.patch(
        "/api/ai/policy",
        json={
            "privacy_mode": "local_only",
            "chat_provider_id": provider_id,
            "auto_tagging": True,
            "auto_enrichment": False,
        },
    )
    assert policy.status_code == 200, policy.text
    assert policy.json()["auto_tagging"] is True
    return provider_id


async def _upload_and_extract(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    *,
    filename: str,
    content: bytes,
) -> uuid.UUID:
    response = await auth_client.post(
        "/api/documents/upload",
        files={"file": (filename, content, "text/plain")},
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


async def _run_suggestion_job(db_session: AsyncSession, doc_id: uuid.UUID) -> dict:
    suggest_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.METADATA_SUGGESTION,
            )
        )
    ).scalar_one()
    suggest_job.status = JobStatus.RUNNING
    result = await process_metadata_suggestion(db_session, suggest_job)
    suggest_job.status = JobStatus.COMPLETED
    await db_session.commit()
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metadata_suggestion_creates_folder_and_tag_rows(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Core unit of the pipeline: mock LLM → pending folder + tags suggestions."""
    _banner("AI filing - suggestion creation (mocked LLM)")
    await _enable_auto_tagging(auth_client, db_session)
    _step(1, "Enabled auto_tagging + local chat provider")

    adapter = _MockFilingAdapter(wrap_in_fence=True)
    monkeypatch.setattr(
        "lesspaper_ngl.workers.processor.get_adapter",
        lambda _provider, api_key=None: adapter,
    )

    text = (
        b"Allianz car insurance renewal notice for policy MY-99821.\n"
        b"Premium due: RM 1,240. Coverage period 2026-01-01 to 2026-12-31.\n"
        b"Please renew before the expiry date to avoid coverage lapse.\n"
    )
    doc_id = await _upload_and_extract(
        auth_client,
        db_session,
        filename="allianz-renewal.txt",
        content=text,
    )
    _step(2, "Uploaded + extracted text", str(doc_id))

    # Extraction should have enqueued METADATA_SUGGESTION when auto_tagging is on
    suggest_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.METADATA_SUGGESTION,
            )
        )
    ).scalar_one_or_none()
    assert suggest_job is not None, "METADATA_SUGGESTION was not enqueued after extraction"
    _step(3, "METADATA_SUGGESTION job enqueued", suggest_job.id.hex[:8])

    result = await _run_suggestion_job(db_session, doc_id)
    _step(4, "Ran metadata suggestion", json.dumps(result))
    assert result.get("suggestions", 0) >= 2

    listed = await auth_client.get(
        "/api/ai/suggestions",
        params={"document_id": str(doc_id), "status": "pending"},
    )
    assert listed.status_code == 200, listed.text
    suggestions = listed.json()
    _step(5, f"Listed {len(suggestions)} pending suggestion(s)")
    _print_suggestions(suggestions)

    by_field = {s["field"]: s for s in suggestions}
    assert "folder" in by_field, "folder suggestion missing - check parser / path regex"
    assert "title" in by_field
    tag_rows = [s for s in suggestions if s["field"] == "tags"]
    assert len(tag_rows) == 3, "expected one tags suggestion per tag name"
    assert {s["value"].get("tag_names", [None])[0] for s in tag_rows} == {
        "lppsa",
        "refinance",
        "housing-loan",
    }
    assert all(isinstance(s.get("confidence"), (int, float)) for s in tag_rows)
    assert by_field["folder"].get("confidence") == 0.94
    assert by_field["title"].get("confidence") == 0.9

    folder_val = by_field["folder"]["value"]
    assert folder_val.get("path") == "Finance / Insurance"
    assert folder_val.get("create") is True

    detail = await auth_client.get(f"/api/documents/{doc_id}")
    body = detail.json()
    _step(6, "Document after suggest (suggestions NOT auto-applied)")
    _kv("inbox_status", body.get("inbox_status"))
    _kv("pending_folder_path", body.get("pending_folder_path"))
    _kv("tags", [t["name"] for t in body.get("tags") or []])
    assert body["pending_folder_path"] is None
    assert body.get("tags") in (None, [])
    assert body["inbox_status"] in ("ready", "needs_review")


@pytest.mark.asyncio
async def test_accept_folder_and_tags_then_process(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full visual path: suggest → accept folder/tags → Process → library folder."""
    _banner("AI filing - accept folder/tags → Process (E2E)")
    await _enable_auto_tagging(auth_client, db_session)

    adapter = _MockFilingAdapter()
    monkeypatch.setattr(
        "lesspaper_ngl.workers.processor.get_adapter",
        lambda _provider, api_key=None: adapter,
    )

    content = (
        b"Insurance schedule for Allianz motor policy.\n"
        b"Insured vehicle: Proton Saga. Annual premium RM 980.\n"
        b"Renewal reminder - please file under Finance / Insurance.\n"
    )
    doc_id = await _upload_and_extract(
        auth_client,
        db_session,
        filename="motor-schedule.txt",
        content=content,
    )
    _step(1, "Uploaded + extracted", str(doc_id))

    result = await _run_suggestion_job(db_session, doc_id)
    _step(2, "Suggestions created", json.dumps(result))

    listed = await auth_client.get(
        "/api/ai/suggestions",
        params={"document_id": str(doc_id)},
    )
    suggestions = listed.json()
    _print_suggestions(suggestions)
    by_field = {s["field"]: s for s in suggestions}

    # Accept title
    title_acc = await auth_client.post(
        f"/api/ai/suggestions/{by_field['title']['id']}/accept"
    )
    assert title_acc.status_code == 200, title_acc.text
    _step(3, "Accepted title", title_acc.json()["value"])

    # Accept folder (intent only - pending path)
    folder_acc = await auth_client.post(
        f"/api/ai/suggestions/{by_field['folder']['id']}/accept"
    )
    assert folder_acc.status_code == 200, folder_acc.text
    _step(4, "Accepted folder suggestion", folder_acc.json()["value"])

    # Accept tags (one suggestion per tag)
    tag_rows = [s for s in suggestions if s["field"] == "tags"]
    assert len(tag_rows) == 3
    for row in tag_rows:
        tags_acc = await auth_client.post(f"/api/ai/suggestions/{row['id']}/accept")
        assert tags_acc.status_code == 200, tags_acc.text
    _step(5, "Accepted tag suggestions", [r["value"] for r in tag_rows])

    after_accept = await auth_client.get(f"/api/documents/{doc_id}")
    body = after_accept.json()
    _step(6, "Document after accept")
    _kv("title", body.get("title"))
    _kv("pending_folder_path", body.get("pending_folder_path"))
    _kv("folder_id", body.get("folder_id"))
    _kv("tags", [t["name"] for t in body.get("tags") or []])
    _kv("needs_review", body.get("needs_review"))
    _kv("inbox_status", body.get("inbox_status"))

    assert body["title"] == "LPPSA Refinance Summary"
    assert body["pending_folder_path"] == "Finance / Insurance"
    tag_names = {t["name"].lower() for t in body.get("tags") or []}
    assert {"lppsa", "refinance", "housing-loan"} <= tag_names
    assert body["inbox"] is True
    assert body["inbox_status"] == "ready"

    # Process into library
    processed = await auth_client.post(
        "/api/documents/process",
        json={"document_ids": [str(doc_id)]},
    )
    assert processed.status_code == 200, processed.text
    _step(7, "Process result", processed.json())

    final = await auth_client.get(f"/api/documents/{doc_id}")
    final_body = final.json()
    _step(8, "Document after Process")
    _kv("inbox", final_body.get("inbox"))
    _kv("folder_path", final_body.get("folder_path"))
    _kv("pending_folder_path", final_body.get("pending_folder_path"))
    _kv("tags", [t["name"] for t in final_body.get("tags") or []])

    assert final_body["inbox"] is False
    assert final_body["pending_folder_path"] is None
    assert "Finance" in (final_body.get("folder_path") or "")
    assert "Insurance" in (final_body.get("folder_path") or "")

    # Suggestions marked accepted
    rows = (
        await db_session.execute(
            select(AISuggestion).where(AISuggestion.document_id == doc_id)
        )
    ).scalars().all()
    statuses = {r.field: r.status for r in rows}
    tag_statuses = [r.status for r in rows if r.field == "tags"]
    _step(9, "Suggestion statuses", {k: v.value for k, v in statuses.items()})
    assert statuses.get("folder") == SuggestionStatus.ACCEPTED
    assert tag_statuses and all(s == SuggestionStatus.ACCEPTED for s in tag_statuses)
    print("\n  ✓ Folder + tag suggestions work end-to-end when accepted in UI/API.\n")


@pytest.mark.asyncio
async def test_reject_folder_leaves_document_unfiled(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_auto_tagging(auth_client, db_session)
    monkeypatch.setattr(
        "lesspaper_ngl.workers.processor.get_adapter",
        lambda _provider, api_key=None: _MockFilingAdapter(),
    )
    doc_id = await _upload_and_extract(
        auth_client,
        db_session,
        filename="reject-me.txt",
        content=b"A short insurance note with enough text for suggestions to run.\n" * 2,
    )
    await _run_suggestion_job(db_session, doc_id)

    listed = await auth_client.get(
        "/api/ai/suggestions",
        params={"document_id": str(doc_id)},
    )
    folder = next(s for s in listed.json() if s["field"] == "folder")
    rejected = await auth_client.post(f"/api/ai/suggestions/{folder['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    detail = await auth_client.get(f"/api/documents/{doc_id}")
    assert detail.json()["pending_folder_path"] is None


# ---------------------------------------------------------------------------
# Live LM Studio (optional)
# ---------------------------------------------------------------------------

_LIVE_BASE = os.environ.get("FOLIUM_LIVE_AI_URL", "http://192.168.1.109:1234/v1")
_LIVE_CHAT_MODEL = os.environ.get(
    "FOLIUM_LIVE_AI_CHAT_MODEL",
    "qwen3.5-9b-deepseek-v4-flash",
)


def _lm_studio_reachable() -> bool:
    if os.environ.get("FOLIUM_LIVE_AI", "").strip() not in {"1", "true", "yes"}:
        return False
    try:
        r = httpx.get(f"{_LIVE_BASE.rstrip('/')}/models", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.live_ai
@pytest.mark.skipif(
    not _lm_studio_reachable(),
    reason="Set FOLIUM_LIVE_AI=1 and ensure LM Studio is reachable",
)
async def test_live_lm_studio_folder_and_tag_suggestions(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Hit a real LM Studio chat model and print folder/tag suggestions."""
    _banner(f"LIVE AI - {_LIVE_BASE} / {_LIVE_CHAT_MODEL}")

    provider = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "pytest-lm-studio",
            "kind": "openai_compatible",
            "base_url": _LIVE_BASE,
            "is_local": True,
            "chat_model": _LIVE_CHAT_MODEL,
            "max_output_tokens": 4096,
        },
    )
    assert provider.status_code == 201, provider.text
    provider_id = provider.json()["id"]
    _step(1, "Created openai_compatible provider", provider_id)

    row = await db_session.get(AIProvider, uuid.UUID(provider_id))
    assert row is not None
    row.last_probe_status = "available"
    await db_session.commit()

    policy = await auth_client.patch(
        "/api/ai/policy",
        json={
            "privacy_mode": "local_only",
            "chat_provider_id": provider_id,
            "auto_tagging": True,
        },
    )
    assert policy.status_code == 200, policy.text
    _step(2, "Policy: auto_tagging on")

    content = (
        b"Allianz motor insurance renewal notice.\n"
        b"Policy number MY-INS-4421. Premium RM 1,150 due 15 September 2026.\n"
        b"Vehicle: Toyota Vios. Please renew to keep coverage active.\n"
        b"Contact: Allianz General Insurance Malaysia.\n"
    )
    doc_id = await _upload_and_extract(
        auth_client,
        db_session,
        filename="live-allianz.txt",
        content=content,
    )
    _step(3, "Uploaded + extracted", str(doc_id))

    suggest_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.METADATA_SUGGESTION,
            )
        )
    ).scalar_one_or_none()
    assert suggest_job is not None
    _step(4, "Calling LM Studio for METADATA_SUGGESTION...")

    result = await _run_suggestion_job(db_session, doc_id)
    _step(5, "Job result", json.dumps(result))
    assert not result.get("skipped"), f"suggestion skipped: {result}"

    listed = await auth_client.get(
        "/api/ai/suggestions",
        params={"document_id": str(doc_id)},
    )
    suggestions = listed.json()
    _step(6, f"Pending suggestions from live model ({len(suggestions)})")
    _print_suggestions(suggestions)

    fields = {s["field"] for s in suggestions}
    assert "folder" in fields or "tags" in fields, (
        "Live model returned neither folder nor tags - check prompt/parser/output"
    )
    print("\n  ✓ Live LM Studio produced at least one filing suggestion.\n")
