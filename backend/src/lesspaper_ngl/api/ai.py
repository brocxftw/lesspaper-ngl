"""AI provider, policy, usage, and suggestion endpoints."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.assignments import ResolvedAssignment, ensure_assignments, resolve_assignment
from lesspaper_ngl.ai.model_discovery import classify_discovered_models
from lesspaper_ngl.ai.profiles import PROFILE_PRESETS
from lesspaper_ngl.ai.registry import get_adapter
from lesspaper_ngl.ai.url_validation import validate_provider_base_url
from lesspaper_ngl.api.schemas import (
    AIAssignmentOut,
    AIAssignmentUpdate,
    AICapabilitiesOut,
    AICapabilityHealthOut,
    AIHealthOut,
    AIPolicyOut,
    AIPolicyUpdate,
    AIProviderCreate,
    AIProviderModelOut,
    AIProviderModelsOut,
    AIProviderOut,
    AIProviderProbeOut,
    AIProviderUpdate,
    AIUsageSummary,
    MessageOut,
    SuggestionOut,
)
from lesspaper_ngl.auth.deps import AdminUser, CurrentUser, SafeSession
from lesspaper_ngl.bootstrap import ensure_ai_settings
from lesspaper_ngl.core.exceptions import ConflictError, NotFoundError, ValidationError
from lesspaper_ngl.core.redaction import redact_text
from lesspaper_ngl.core.security import decrypt_secret, encrypt_secret, mask_secret
from lesspaper_ngl.db.session import get_db, session_scope
from lesspaper_ngl.models import (
    AIModelAssignment,
    AIProfileName,
    AIProvider,
    AISettings,
    AISuggestion,
    AIWorkloadRole,
    Correspondent,
    Document,
    DocumentType,
    FolderKind,
    PrivacyMode,
    ProviderKind,
    SuggestionStatus,
    Tag,
)
from lesspaper_ngl.services import documents as doc_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _document_has_manual_destination(doc: Document) -> bool:
    pending = doc_service.get_pending_folder_path(doc)
    in_system_inbox = doc.folder is not None and doc.folder.kind == FolderKind.INBOX
    return bool(pending) or (doc.folder is not None and not in_system_inbox)


def _provider_out(provider: AIProvider) -> AIProviderOut:
    has_key = provider.encrypted_api_key is not None
    masked: str | None = None
    if has_key:
        try:
            masked = mask_secret(decrypt_secret(provider.encrypted_api_key))  # type: ignore[arg-type]
        except ValueError:
            masked = "••••"
    return AIProviderOut(
        id=provider.id,
        name=provider.name,
        kind=provider.kind.value,
        base_url=provider.base_url,
        has_api_key=has_key,
        api_key_masked=masked,
        is_local=provider.is_local,
        enabled=provider.enabled,
        chat_model=provider.chat_model,
        embedding_model=provider.embedding_model,
        vision_model=provider.vision_model,
        context_window=provider.context_window,
        max_output_tokens=provider.max_output_tokens,
        supports_tools=provider.supports_tools,
        supports_vision=provider.supports_vision,
        supports_structured_output=provider.supports_structured_output,
        supports_embeddings=provider.supports_embeddings,
        embedding_max_input_tokens=provider.embedding_max_input_tokens,
        embedding_recommended_chunk_tokens=provider.embedding_recommended_chunk_tokens,
        embedding_batch_size=provider.embedding_batch_size,
        embedding_max_batch_size=provider.embedding_max_batch_size,
        embedding_concurrency=provider.embedding_concurrency,
        no_training=provider.no_training,
        zero_retention=provider.zero_retention,
        last_probe_status=provider.last_probe_status,
        last_probe_error=provider.last_probe_error,
        last_probe_latency_ms=provider.last_probe_latency_ms,
        last_probe_model_count=provider.last_probe_model_count,
        last_probed_at=provider.last_probed_at,
        last_success_at=provider.last_success_at,
    )


def _policy_out(settings_row: AISettings) -> AIPolicyOut:
    return AIPolicyOut(
        privacy_mode=settings_row.privacy_mode.value,
        profile=settings_row.profile.value,
        chat_provider_id=settings_row.chat_provider_id,
        embedding_provider_id=settings_row.embedding_provider_id,
        vision_provider_id=settings_row.vision_provider_id,
        allow_remote_embeddings=settings_row.allow_remote_embeddings,
        allow_remote_qa=settings_row.allow_remote_qa,
        allow_remote_vision=settings_row.allow_remote_vision,
        warn_before_remote=settings_row.warn_before_remote,
        block_remote_ai=settings_row.block_remote_ai,
        auto_enrichment=settings_row.auto_enrichment,
        auto_tagging=settings_row.auto_tagging,
        retrieved_chunks=settings_row.retrieved_chunks,
        max_context_tokens=settings_row.max_context_tokens,
        max_output_tokens=settings_row.max_output_tokens,
        conversation_history_tokens=settings_row.conversation_history_tokens,
        parallel_llm_calls=settings_row.parallel_llm_calls,
        semantic_min_score=settings_row.semantic_min_score,
        active_embedding_provider=settings_row.active_embedding_provider,
        active_embedding_model=settings_row.active_embedding_model,
        active_embedding_dimension=settings_row.active_embedding_dimension,
    )


def _kind_from_str(kind: str) -> ProviderKind:
    try:
        return ProviderKind(kind)
    except ValueError as exc:
        raise ValidationError(f"Unsupported provider kind: {kind}") from exc


# ---- Providers ----


@router.get("/providers", response_model=list[AIProviderOut])
async def list_providers(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AIProviderOut]:
    providers = (await db.execute(select(AIProvider).order_by(AIProvider.name))).scalars().all()
    return [_provider_out(p) for p in providers]


@router.post("/providers", response_model=AIProviderOut, status_code=201)
async def create_provider(
    body: AIProviderCreate,
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIProviderOut:
    existing = (
        await db.execute(select(AIProvider).where(AIProvider.name == body.name))
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Provider name already exists")

    validated = validate_provider_base_url(body.base_url)
    provider = AIProvider(
        name=body.name,
        kind=_kind_from_str(body.kind),
        base_url=validated.url,
        is_local=body.is_local or validated.is_local,
        chat_model=body.chat_model,
        embedding_model=body.embedding_model,
        vision_model=body.vision_model,
        context_window=body.context_window,
        max_output_tokens=body.max_output_tokens,
        supports_tools=body.supports_tools,
        supports_vision=body.supports_vision,
        supports_structured_output=body.supports_structured_output,
        supports_embeddings=body.supports_embeddings,
        embedding_max_input_tokens=body.embedding_max_input_tokens,
        embedding_recommended_chunk_tokens=body.embedding_recommended_chunk_tokens,
        embedding_batch_size=body.embedding_batch_size,
        embedding_max_batch_size=body.embedding_max_batch_size,
        embedding_concurrency=body.embedding_concurrency,
        no_training=body.no_training,
        zero_retention=body.zero_retention,
    )
    if body.api_key:
        provider.encrypted_api_key = encrypt_secret(body.api_key)
    db.add(provider)
    await db.flush()
    return _provider_out(provider)


@router.get("/providers/{provider_id}", response_model=AIProviderOut)
async def get_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIProviderOut:
    provider = await db.get(AIProvider, provider_id)
    if provider is None:
        raise NotFoundError("Provider not found")
    return _provider_out(provider)


@router.patch("/providers/{provider_id}", response_model=AIProviderOut)
async def update_provider(
    provider_id: uuid.UUID,
    body: AIProviderUpdate,
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIProviderOut:
    provider = await db.get(AIProvider, provider_id)
    if provider is None:
        raise NotFoundError("Provider not found")

    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        conflict = (
            await db.execute(
                select(AIProvider).where(
                    AIProvider.name == data["name"],
                    AIProvider.id != provider_id,
                )
            )
        ).scalar_one_or_none()
        if conflict:
            raise ConflictError("Provider name already exists")
        provider.name = data["name"]

    if "base_url" in data and data["base_url"] is not None:
        validated = validate_provider_base_url(data["base_url"])
        provider.base_url = validated.url
        if body.is_local is None:
            provider.is_local = validated.is_local

    for field in (
        "is_local",
        "enabled",
        "chat_model",
        "embedding_model",
        "vision_model",
        "context_window",
        "max_output_tokens",
        "supports_tools",
        "supports_vision",
        "supports_structured_output",
        "supports_embeddings",
        "embedding_max_input_tokens",
        "embedding_recommended_chunk_tokens",
        "embedding_batch_size",
        "embedding_max_batch_size",
        "embedding_concurrency",
        "no_training",
        "zero_retention",
    ):
        if field in data and data[field] is not None:
            setattr(provider, field, data[field])

    if body.clear_api_key:
        provider.encrypted_api_key = None
    elif body.api_key:
        provider.encrypted_api_key = encrypt_secret(body.api_key)

    await db.flush()
    return _provider_out(provider)


@router.delete("/providers/{provider_id}", response_model=MessageOut)
async def delete_provider(
    provider_id: uuid.UUID,
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    provider = await db.get(AIProvider, provider_id)
    if provider is None:
        raise NotFoundError("Provider not found")
    dependencies = (
        (
            await db.execute(
                select(AIModelAssignment.role).where(AIModelAssignment.provider_id == provider_id)
            )
        )
        .scalars()
        .all()
    )
    if dependencies:
        roles = ", ".join(sorted(role.value for role in dependencies))
        raise ConflictError(f"Provider is assigned to: {roles}. Reassign those workloads first.")
    await db.delete(provider)
    return MessageOut(message="Provider deleted")


async def _discover_models(provider: AIProvider) -> list[AIProviderModelOut] | None:
    if provider.kind not in {
        ProviderKind.OPENAI_COMPATIBLE,
        ProviderKind.OPENAI,
        ProviderKind.OPENROUTER,
        ProviderKind.OLLAMA,
    }:
        return None
    headers: dict[str, str] = {}
    if provider.encrypted_api_key:
        headers["Authorization"] = f"Bearer {decrypt_secret(provider.encrypted_api_key)}"
    url = provider.base_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    models_url = f"{url}/models"
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        # OpenRouter defaults to text-only; request all modalities so embeddings appear.
        response = await client.get(models_url, params={"output_modalities": "all"})
        if response.status_code >= 400:
            response = await client.get(models_url)
        response.raise_for_status()
        payload = response.json()
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return []
    items = [item for item in data if isinstance(item, dict)]
    classified = classify_discovered_models(items)
    return [AIProviderModelOut(id=row["id"], kind=row["kind"]) for row in classified]


async def _load_provider_detached(provider_id: uuid.UUID) -> AIProvider:
    async with session_scope() as session:
        provider = await session.get(AIProvider, provider_id)
        if provider is None:
            raise NotFoundError("Provider not found")
        session.expunge(provider)
        return provider


async def _persist_manual_probe(
    provider_id: uuid.UUID,
    *,
    status: str,
    error: str | None,
    latency_ms: int,
    tested_at: datetime,
    model_count: int | None = None,
    success: bool = False,
) -> None:
    async with session_scope() as session:
        row = await session.get(AIProvider, provider_id)
        if row is None:
            return
        row.last_probe_status = status
        row.last_probe_error = error
        row.last_probe_latency_ms = latency_ms
        row.last_probe_model_count = model_count
        row.last_probed_at = tested_at
        if success:
            row.last_success_at = tested_at


@router.get("/providers/{provider_id}/models", response_model=AIProviderModelsOut)
async def discover_provider_models(
    provider_id: uuid.UUID,
    _admin: AdminUser,
) -> AIProviderModelsOut:
    provider = await _load_provider_detached(provider_id)
    try:
        models = await _discover_models(provider)
    except Exception as exc:
        raise ValidationError(redact_text(f"Model discovery failed: {exc}")[:500]) from exc
    if models is None:
        return AIProviderModelsOut(
            models=[],
            discoverable=False,
            message="This provider does not expose model discovery.",
        )
    return AIProviderModelsOut(models=models, discoverable=True)


@router.post("/providers/{provider_id}/test", response_model=AIProviderProbeOut)
async def test_provider_connection(
    provider_id: uuid.UUID,
    _sess: SafeSession,
    _admin: AdminUser,
) -> AIProviderProbeOut:
    provider = await _load_provider_detached(provider_id)
    adapter = get_adapter(provider)
    started = time.perf_counter()
    tested_at = datetime.now(UTC)
    try:
        ok = await adapter.test_connection()
        models = await _discover_models(provider)
    except Exception as exc:
        latency = round((time.perf_counter() - started) * 1000)
        error = redact_text(str(exc))[:512]
        await _persist_manual_probe(
            provider_id,
            status="offline",
            error=error,
            latency_ms=latency,
            tested_at=tested_at,
        )
        return AIProviderProbeOut(
            status="offline",
            latency_ms=latency,
            model_count=None,
            tested_at=tested_at,
            message=f"Provider connection failed: {error}",
        )
    finally:
        await adapter.aclose()
    if not ok:
        latency = round((time.perf_counter() - started) * 1000)
        error = "Provider connection test failed"
        await _persist_manual_probe(
            provider_id,
            status="offline",
            error=error,
            latency_ms=latency,
            tested_at=tested_at,
        )
        return AIProviderProbeOut(
            status="offline",
            latency_ms=latency,
            model_count=None,
            tested_at=tested_at,
            message=error,
        )
    latency = round((time.perf_counter() - started) * 1000)
    model_count = len(models) if models is not None else None
    await _persist_manual_probe(
        provider_id,
        status="available",
        error=None,
        latency_ms=latency,
        tested_at=tested_at,
        model_count=model_count,
        success=True,
    )
    return AIProviderProbeOut(
        status="available",
        latency_ms=latency,
        model_count=model_count,
        tested_at=tested_at,
        message="Connection successful",
    )


def _assignment_out(
    role: AIWorkloadRole,
    resolved: ResolvedAssignment,
    settings_row: AISettings,
) -> AIAssignmentOut:
    provider = resolved.provider
    if provider is None or not resolved.model:
        status = "unconfigured"
    elif not provider.enabled:
        status = "disabled"
    elif provider.last_probe_status == "offline":
        status = "offline"
    else:
        status = "configured"
    return AIAssignmentOut(
        role=role.value,
        provider_id=provider.id if provider else None,
        provider_name=provider.name if provider else None,
        model=resolved.model,
        is_local=provider.is_local if provider else None,
        enabled=bool(provider and provider.enabled),
        status=status,
        embedding_dimension=(
            settings_row.active_embedding_dimension if role == AIWorkloadRole.EMBEDDING else None
        ),
        legacy_fallback=resolved.legacy_fallback,
    )


@router.get("/assignments", response_model=list[AIAssignmentOut])
async def list_assignments(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AIAssignmentOut]:
    settings_row = await ensure_ai_settings(db)
    await ensure_assignments(db)
    return [
        _assignment_out(role, await resolve_assignment(db, role), settings_row)
        for role in AIWorkloadRole
    ]


@router.patch("/assignments", response_model=AIAssignmentOut)
async def update_assignment(
    body: AIAssignmentUpdate,
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIAssignmentOut:
    role = AIWorkloadRole(body.role)
    rows = {row.role: row for row in await ensure_assignments(db)}
    row = rows[role]
    provider = await db.get(AIProvider, body.provider_id) if body.provider_id else None
    if body.provider_id and provider is None:
        raise ValidationError("Provider not found")
    if provider and not provider.enabled:
        raise ValidationError("Disabled providers cannot be assigned")
    model = body.model.strip() if body.model else None
    if provider and not model:
        raise ValidationError("A model ID is required")
    settings_row = await ensure_ai_settings(db)
    if provider and not provider.is_local:
        remote_allowed = {
            AIWorkloadRole.INDEXING: settings_row.allow_remote_qa,
            AIWorkloadRole.CHAT: settings_row.allow_remote_qa,
            AIWorkloadRole.EMBEDDING: settings_row.allow_remote_embeddings,
            AIWorkloadRole.VISION: settings_row.allow_remote_vision,
        }[role]
        if (
            settings_row.privacy_mode == PrivacyMode.LOCAL_ONLY
            or settings_row.block_remote_ai
            or not remote_allowed
        ):
            raise ValidationError("The current AI Policy blocks this remote workload assignment")
    changed = row.provider_id != (provider.id if provider else None) or row.model != model
    row.provider_id = provider.id if provider else None
    row.model = model
    if role == AIWorkloadRole.EMBEDDING and provider and model:
        provider.supports_embeddings = True
        provider.embedding_model = model
    if role == AIWorkloadRole.EMBEDDING and changed:
        settings_row.active_embedding_provider = None
        settings_row.active_embedding_model = None
        settings_row.active_embedding_dimension = None
    if role == AIWorkloadRole.INDEXING and provider and model:
        settings_row.auto_tagging = True
    await db.flush()
    return _assignment_out(role, await resolve_assignment(db, role), settings_row)


@router.get("/capabilities", response_model=AICapabilitiesOut)
async def get_capabilities(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AICapabilitiesOut:
    settings_row = await ensure_ai_settings(db)
    chat = await resolve_assignment(db, AIWorkloadRole.CHAT)
    embedding = await resolve_assignment(db, AIWorkloadRole.EMBEDDING)
    return AICapabilitiesOut(
        chat_available=bool(chat.provider and chat.provider.enabled and chat.model),
        embeddings_available=bool(
            embedding.provider and embedding.provider.enabled and embedding.model
        ),
        auto_tagging=settings_row.auto_tagging,
        auto_enrichment=settings_row.auto_enrichment,
        warn_before_remote_chat=bool(
            settings_row.warn_before_remote and chat.provider and not chat.provider.is_local
        ),
        chat_is_local=chat.provider.is_local if chat.provider else None,
        privacy_mode=settings_row.privacy_mode.value,
    )


def _capability_health_out(cap) -> AICapabilityHealthOut:
    return AICapabilityHealthOut(
        status=cap.status,
        provider=cap.provider,
        model=cap.model,
        latency_ms=cap.latency_ms,
        last_checked=cap.last_checked,
        error=cap.error,
    )


@router.get("/health", response_model=AIHealthOut)
async def get_ai_health(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIHealthOut:
    """Cached per-capability AI/OCR health (probes run in the worker every 10s)."""
    from lesspaper_ngl.ai.health import build_ai_health_report

    report = await build_ai_health_report(db)
    return AIHealthOut(
        ocr=_capability_health_out(report.ocr),
        indexing=_capability_health_out(report.indexing),
        embedding=_capability_health_out(report.embedding),
        chat=_capability_health_out(report.chat),
        auto_tagging=report.auto_tagging,
        auto_enrichment=report.auto_enrichment,
    )


# ---- Policy ----


@router.get("/policy", response_model=AIPolicyOut)
async def get_policy(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIPolicyOut:
    settings_row = await ensure_ai_settings(db)
    return _policy_out(settings_row)


@router.patch("/policy", response_model=AIPolicyOut)
async def update_policy(
    body: AIPolicyUpdate,
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIPolicyOut:
    settings_row = await ensure_ai_settings(db)
    data = body.model_dump(exclude_unset=True)

    if "privacy_mode" in data and data["privacy_mode"] is not None:
        settings_row.privacy_mode = PrivacyMode(data["privacy_mode"])
    if "profile" in data and data["profile"] is not None:
        settings_row.profile = AIProfileName(data["profile"])
        if settings_row.profile != AIProfileName.CUSTOM:
            preset = PROFILE_PRESETS[settings_row.profile.value]
            settings_row.retrieved_chunks = preset["retrieved_chunks"]
            settings_row.max_context_tokens = preset["max_context_tokens"]
            settings_row.max_output_tokens = preset["max_output_tokens"]
            settings_row.conversation_history_tokens = preset["conversation_history_tokens"]
            settings_row.parallel_llm_calls = preset["parallel_llm_calls"]

    for field in (
        "chat_provider_id",
        "embedding_provider_id",
        "vision_provider_id",
        "allow_remote_embeddings",
        "allow_remote_qa",
        "allow_remote_vision",
        "warn_before_remote",
        "block_remote_ai",
        "auto_enrichment",
        "auto_tagging",
        "retrieved_chunks",
        "max_context_tokens",
        "max_output_tokens",
        "conversation_history_tokens",
        "parallel_llm_calls",
    ):
        if field in data and data[field] is not None:
            setattr(settings_row, field, data[field])

    # Allow explicitly clearing the floor by sending null.
    if "semantic_min_score" in data:
        score = data["semantic_min_score"]
        if score is None:
            settings_row.semantic_min_score = None
        else:
            value = float(score)
            if value < -1.0 or value > 1.0:
                raise ValidationError("semantic_min_score must be between -1 and 1")
            settings_row.semantic_min_score = value

    if settings_row.profile != AIProfileName.CUSTOM and any(
        f in data
        for f in (
            "retrieved_chunks",
            "max_context_tokens",
            "max_output_tokens",
            "conversation_history_tokens",
            "parallel_llm_calls",
        )
    ):
        settings_row.profile = AIProfileName.CUSTOM

    if settings_row.embedding_provider_id is not None:
        embed_provider = await db.get(AIProvider, settings_row.embedding_provider_id)
        if embed_provider is not None:
            settings_row.active_embedding_provider = embed_provider.name
            settings_row.active_embedding_model = embed_provider.embedding_model

    remote_assignments = (
        await db.execute(
            select(AIModelAssignment, AIProvider)
            .join(AIProvider, AIProvider.id == AIModelAssignment.provider_id)
            .where(AIProvider.is_local.is_(False))
        )
    ).all()
    conflicts: list[str] = []
    for assignment, _provider in remote_assignments:
        allowed = {
            AIWorkloadRole.INDEXING: settings_row.allow_remote_qa,
            AIWorkloadRole.CHAT: settings_row.allow_remote_qa,
            AIWorkloadRole.EMBEDDING: settings_row.allow_remote_embeddings,
            AIWorkloadRole.VISION: settings_row.allow_remote_vision,
        }[assignment.role]
        if (
            settings_row.privacy_mode == PrivacyMode.LOCAL_ONLY
            or settings_row.block_remote_ai
            or not allowed
        ):
            conflicts.append(assignment.role.value)
    if conflicts:
        raise ValidationError(
            "AI Policy conflicts with remote assignments: "
            + ", ".join(sorted(conflicts))
            + ". Reassign them to local providers first."
        )

    # Keep the legacy provider fields write-compatible for one release, while
    # all runtime resolution remains assignment-only.
    legacy_assignment_fields = {
        "chat_provider_id": (
            (AIWorkloadRole.INDEXING, AIWorkloadRole.CHAT),
            "chat_model",
        ),
        "embedding_provider_id": ((AIWorkloadRole.EMBEDDING,), "embedding_model"),
        "vision_provider_id": ((AIWorkloadRole.VISION,), "vision_model"),
    }
    if any(field in data for field in legacy_assignment_fields):
        assignments = {row.role: row for row in await ensure_assignments(db)}
        for field, (roles, model_field) in legacy_assignment_fields.items():
            if field not in data:
                continue
            provider_id = getattr(settings_row, field)
            provider = await db.get(AIProvider, provider_id) if provider_id else None
            for role in roles:
                assignments[role].provider_id = provider.id if provider else None
                assignments[role].model = getattr(provider, model_field, None) if provider else None

    await db.flush()
    return _policy_out(settings_row)


# ---- Usage ----


@router.get("/usage", response_model=AIUsageSummary)
async def get_usage(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    range: str = Query(default="month", pattern="^(today|7d|30d|month)$"),
    interval: str | None = Query(default=None, pattern="^(hour|day)$"),
) -> AIUsageSummary:
    from lesspaper_ngl.models import AIUsage

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    starts = {
        "today": today_start,
        "7d": today_start - timedelta(days=6),
        "30d": today_start - timedelta(days=29),
        "month": today_start.replace(day=1),
    }
    start = starts[range]
    effective_interval = interval or ("hour" if range == "today" else "day")
    trunc = func.date_trunc(effective_interval, AIUsage.created_at)
    where = (AIUsage.created_at >= start, AIUsage.created_at <= now)
    total = (
        await db.execute(
            select(
                func.count(AIUsage.id),
                func.sum(AIUsage.input_tokens),
                func.sum(AIUsage.output_tokens),
                func.sum(AIUsage.duration_ms),
                func.sum(func.coalesce(AIUsage.reported_cost, AIUsage.estimated_cost)),
                func.count(func.coalesce(AIUsage.reported_cost, AIUsage.estimated_cost)),
                func.count(AIUsage.id).filter(AIUsage.is_local.is_(False)),
                func.min(AIUsage.cost_currency),
                func.count(func.distinct(AIUsage.cost_currency)),
            ).where(*where)
        )
    ).one()
    requests, cost_rows, remote_rows = int(total[0]), int(total[5]), int(total[6])
    if requests and remote_rows == 0:
        coverage = "local_only"
    elif cost_rows == 0:
        coverage = "none"
    elif cost_rows < remote_rows:
        coverage = "partial"
    else:
        coverage = "complete"
    currency = total[7] if int(total[8]) == 1 else None

    series_rows = (
        await db.execute(
            select(
                trunc.label("bucket"),
                func.count(AIUsage.id),
                func.sum(AIUsage.input_tokens),
                func.sum(AIUsage.output_tokens),
                func.sum(AIUsage.duration_ms),
            )
            .where(*where)
            .group_by(trunc)
            .order_by(trunc)
        )
    ).all()
    provider_rows = (
        await db.execute(
            select(
                AIUsage.provider,
                func.count(AIUsage.id),
                func.sum(AIUsage.input_tokens),
                func.sum(AIUsage.output_tokens),
            )
            .where(*where)
            .group_by(AIUsage.provider)
            .order_by(func.count(AIUsage.id).desc())
        )
    ).all()
    operation_rows = (
        await db.execute(
            select(
                AIUsage.operation,
                func.count(AIUsage.id),
                func.sum(AIUsage.duration_ms),
            )
            .where(*where)
            .group_by(AIUsage.operation)
        )
    ).all()
    workload_names = {
        "embedding": ("embeddings", "Embeddings"),
        "qa": ("chat", "Ask lesspaper-ngl"),
        "summary": ("indexing", "Filing suggestions"),
        "metadata_suggestion": ("indexing", "Filing suggestions"),
    }
    grouped: dict[str, dict[str, int | str | None]] = {}
    for operation, count, duration_ms in operation_rows:
        key, label = workload_names.get(operation, (operation, operation.replace("_", " ").title()))
        bucket = grouped.setdefault(key, {"label": label, "requests": 0, "duration_ms": 0})
        bucket["requests"] = int(bucket["requests"]) + int(count)
        if duration_ms is not None:
            bucket["duration_ms"] = int(bucket["duration_ms"] or 0) + int(duration_ms)

    return AIUsageSummary(
        range=range,
        interval=effective_interval,
        starts_at=start,
        ends_at=now,
        totals={
            "requests": requests,
            "input_tokens": int(total[1]) if total[1] is not None else None,
            "output_tokens": int(total[2]) if total[2] is not None else None,
            "duration_ms": int(total[3]) if total[3] is not None else None,
            "estimated_cost": float(total[4]) if total[4] is not None else None,
            "cost_currency": currency,
            "cost_coverage": coverage,
        },
        time_series=[
            {
                "bucket": row[0],
                "requests": int(row[1]),
                "input_tokens": int(row[2]) if row[2] is not None else None,
                "output_tokens": int(row[3]) if row[3] is not None else None,
                "duration_ms": int(row[4]) if row[4] is not None else None,
            }
            for row in series_rows
        ],
        by_provider=[
            {
                "key": row[0],
                "label": row[0],
                "requests": int(row[1]),
                "input_tokens": int(row[2]) if row[2] is not None else None,
                "output_tokens": int(row[3]) if row[3] is not None else None,
            }
            for row in provider_rows
        ],
        by_workload=[
            {
                "key": key,
                "label": str(entry["label"]),
                "requests": int(entry["requests"]),
                "duration_ms": int(entry["duration_ms"]) if entry["duration_ms"] else None,
            }
            for key, entry in sorted(grouped.items())
        ],
    )


# ---- Suggestions ----


@router.get("/suggestions", response_model=list[SuggestionOut])
async def list_suggestions(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    document_id: uuid.UUID | None = None,
    status: SuggestionStatus | None = SuggestionStatus.PENDING,
) -> list[SuggestionOut]:
    stmt = (
        select(AISuggestion)
        .join(Document, Document.id == AISuggestion.document_id)
        .where(Document.owner_id == _user.id)
        .order_by(AISuggestion.created_at.desc())
    )
    if document_id is not None:
        stmt = stmt.where(AISuggestion.document_id == document_id)
    if status is not None:
        stmt = stmt.where(AISuggestion.status == status)
    rows = (await db.execute(stmt.limit(200))).scalars().all()
    return [
        SuggestionOut(
            id=s.id,
            document_id=s.document_id,
            field=s.field,
            value=s.value,
            status=s.status.value,
            provider=s.provider,
            model=s.model,
            confidence=s.confidence,
        )
        for s in rows
    ]


async def _apply_suggestion(
    db: AsyncSession,
    suggestion: AISuggestion,
    owner_id: uuid.UUID,
) -> None:
    doc = await doc_service.get_document(db, suggestion.document_id, owner_id=owner_id)
    field = suggestion.field
    value = suggestion.value

    if field == "title" and "title" in value:
        doc.title = str(value["title"])
    elif field == "folder":
        if _document_has_manual_destination(doc):
            return
        # Intent only while in Inbox — never create folders here.
        if "folder_id" in value and value["folder_id"]:
            folder_id = uuid.UUID(str(value["folder_id"]))
            await doc_service.move_document(
                db,
                doc.id,
                folder_id,
                owner_id=owner_id,
                preserve_inbox=bool(doc.inbox),
            )
            doc_service.set_pending_folder_path(doc, None)
            if doc.inbox:
                doc.needs_review = False
        elif value.get("create") and value.get("path"):
            doc_service.set_pending_folder_path(doc, str(value["path"]))
            if doc.inbox:
                doc.needs_review = False
        elif value.get("path") and value.get("exists"):
            # Path claimed to exist but no id — store as pending for Process resolution
            doc_service.set_pending_folder_path(doc, str(value["path"]))
            if doc.inbox:
                doc.needs_review = False
    elif field == "document_type" and "document_type_id" in value:
        type_id = uuid.UUID(str(value["document_type_id"]))
        document_type = await db.get(DocumentType, type_id)
        if document_type is None or document_type.owner_id != owner_id:
            raise NotFoundError("Document type not found")
        doc.document_type_id = type_id
    elif field == "correspondent" and "correspondent_id" in value:
        correspondent_id = uuid.UUID(str(value["correspondent_id"]))
        correspondent = await db.get(Correspondent, correspondent_id)
        if correspondent is None or correspondent.owner_id != owner_id:
            raise NotFoundError("Correspondent not found")
        doc.correspondent_id = correspondent_id
    elif field == "tags" and "tag_names" in value:
        names = value["tag_names"]
        if isinstance(names, list):
            from lesspaper_ngl.core.exceptions import ConflictError
            from lesspaper_ngl.services import tags as tag_service

            resolved: list[Tag] = []
            for raw in names:
                if not isinstance(raw, str) or not raw.strip():
                    continue
                name = raw.strip()
                existing = (
                    await db.execute(
                        select(Tag).where(
                            Tag.owner_id == owner_id,
                            Tag.name.ilike(name),
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    resolved.append(existing)
                    continue
                try:
                    created = await tag_service.create_tag(db, name=name, owner_id=owner_id)
                    resolved.append(created)
                except ConflictError:
                    again = (
                        await db.execute(
                            select(Tag).where(
                                Tag.owner_id == owner_id,
                                Tag.name.ilike(name),
                            )
                        )
                    ).scalar_one_or_none()
                    if again is not None:
                        resolved.append(again)
            if resolved:
                existing_ids = {t.id for t in doc.tags}
                doc.tags = list(doc.tags) + [t for t in resolved if t.id not in existing_ids]
    elif field == "notes" and "notes" in value:
        doc.notes = str(value["notes"])
    await db.flush()


@router.post("/suggestions/{suggestion_id}/accept", response_model=SuggestionOut)
async def accept_suggestion(
    suggestion_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuggestionOut:
    suggestion = await db.get(AISuggestion, suggestion_id)
    if suggestion is None:
        raise NotFoundError("Suggestion not found")
    await doc_service.get_document(db, suggestion.document_id, owner_id=_user.id)
    await _apply_suggestion(db, suggestion, _user.id)
    suggestion.status = SuggestionStatus.ACCEPTED
    await db.flush()
    return SuggestionOut(
        id=suggestion.id,
        document_id=suggestion.document_id,
        field=suggestion.field,
        value=suggestion.value,
        status=suggestion.status.value,
        provider=suggestion.provider,
        model=suggestion.model,
        confidence=suggestion.confidence,
    )


@router.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionOut)
async def reject_suggestion(
    suggestion_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuggestionOut:
    suggestion = await db.get(AISuggestion, suggestion_id)
    if suggestion is None:
        raise NotFoundError("Suggestion not found")
    await doc_service.get_document(db, suggestion.document_id, owner_id=_user.id)
    suggestion.status = SuggestionStatus.REJECTED
    await db.flush()
    return SuggestionOut(
        id=suggestion.id,
        document_id=suggestion.document_id,
        field=suggestion.field,
        value=suggestion.value,
        status=suggestion.status.value,
        provider=suggestion.provider,
        model=suggestion.model,
        confidence=suggestion.confidence,
    )
