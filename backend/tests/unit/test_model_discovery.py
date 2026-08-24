"""Unit tests for provider model discovery classification."""

from __future__ import annotations

from lesspaper_ngl.ai.model_discovery import classify_discovered_models, classify_model_kind


def test_classify_openrouter_architecture_embeddings() -> None:
    kind = classify_model_kind(
        "openai/text-embedding-3-small",
        {
            "id": "openai/text-embedding-3-small",
            "architecture": {"output_modalities": ["embeddings"]},
        },
    )
    assert kind == "embedding"


def test_classify_openrouter_architecture_text() -> None:
    kind = classify_model_kind(
        "openai/gpt-4o-mini",
        {
            "id": "openai/gpt-4o-mini",
            "architecture": {"output_modalities": ["text"]},
        },
    )
    assert kind == "chat"


def test_classify_falls_back_to_id_heuristic() -> None:
    assert classify_model_kind("nomic-embed-text") == "embedding"
    assert classify_model_kind("text-embedding-3-small") == "embedding"
    assert classify_model_kind("qwen2.5-7b-instruct") == "chat"


def test_classify_discovered_models_dedupes_and_orders() -> None:
    rows = classify_discovered_models(
        [
            {"id": "z-chat", "architecture": {"output_modalities": ["text"]}},
            {
                "id": "openai/text-embedding-3-small",
                "architecture": {"output_modalities": ["embeddings"]},
            },
            {"id": "a-chat", "architecture": {"output_modalities": ["text"]}},
            {"id": "openai/text-embedding-3-small"},  # duplicate without metadata
        ]
    )
    assert [row["id"] for row in rows] == [
        "openai/text-embedding-3-small",
        "a-chat",
        "z-chat",
    ]
    assert rows[0]["kind"] == "embedding"
    assert rows[1]["kind"] == "chat"
