"""Classify provider model-discovery results as embedding, chat, or other."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

ModelKind = Literal["embedding", "chat", "other"]


class ClassifiedModel(TypedDict):
    id: str
    kind: ModelKind


_EMBEDDING_ID_HINTS = (
    "embed",
    "embedding",
    "bge-",
    "e5-",
    "nomic-embed",
    "mxbai-embed",
    "text-embedding",
    "gte-",
)


def classify_model_kind(model_id: str, raw: dict[str, Any] | None = None) -> ModelKind:
    """Classify a discovered model using provider metadata, then ID heuristics."""
    raw = raw or {}
    architecture = raw.get("architecture")
    if isinstance(architecture, dict):
        outputs = architecture.get("output_modalities")
        if isinstance(outputs, list):
            normalized = {str(item).lower() for item in outputs}
            if "embeddings" in normalized or "embedding" in normalized:
                return "embedding"
            if "text" in normalized:
                return "chat"
            if normalized:
                return "other"

    # Some OpenAI-compatible servers advertise capability flags.
    caps = raw.get("capabilities")
    if isinstance(caps, dict):
        if caps.get("embedding") or caps.get("embeddings"):
            return "embedding"
        if caps.get("completion") or caps.get("chat") or caps.get("completion_chat"):
            return "chat"

    lower = model_id.lower()
    if any(hint in lower for hint in _EMBEDDING_ID_HINTS):
        return "embedding"
    return "chat"


def classify_discovered_models(items: list[dict[str, Any]]) -> list[ClassifiedModel]:
    """Return unique `{id, kind}` rows sorted by kind bucket then id."""
    by_id: dict[str, ModelKind] = {}
    for item in items:
        model_id = item.get("id")
        if not model_id:
            continue
        model_id = str(model_id)
        kind = classify_model_kind(model_id, item)
        # Prefer embedding if any duplicate row classifies as such.
        existing = by_id.get(model_id)
        if existing is None or (kind == "embedding" and existing != "embedding"):
            by_id[model_id] = kind

    kind_order = {"embedding": 0, "chat": 1, "other": 2}
    ordered = sorted(by_id.items(), key=lambda pair: (kind_order[pair[1]], pair[0].lower()))
    return [ClassifiedModel(id=model_id, kind=kind) for model_id, kind in ordered]
