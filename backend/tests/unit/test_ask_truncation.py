"""Ask truncation must not be mislabeled as insufficient evidence."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lesspaper_ngl.ai.base import ChatResult
from lesspaper_ngl.ai.rag import OUTPUT_TRUNCATED_MESSAGE, AskResult, ask
from lesspaper_ngl.core.exceptions import ValidationError
from lesspaper_ngl.models import AIProfileName, PrivacyMode


class _FakeAdapter:
    def __init__(self, result: ChatResult) -> None:
        self._result = result
        self.provider_name = "fake"
        self.is_local = True

    async def chat(self, messages, *, model=None, max_tokens=None, temperature=0.2):
        del messages, model, max_tokens, temperature
        return self._result

    async def aclose(self) -> None:
        return None


def _library_scope() -> SimpleNamespace:
    return SimpleNamespace(
        kind="library",
        document_id=None,
        document_ids=[],
        folder_id=None,
        search_query=None,
    )


def _lightweight_settings() -> SimpleNamespace:
    return SimpleNamespace(
        profile=AIProfileName.LIGHTWEIGHT,
        retrieved_chunks=3,
        max_context_tokens=8000,
        max_output_tokens=1024,
        conversation_history_tokens=2000,
        parallel_llm_calls=1,
        semantic_min_score=None,
        active_embedding_model=None,
        active_embedding_provider=None,
        active_embedding_dimension=None,
        privacy_mode=PrivacyMode.LOCAL_ONLY,
    )


@pytest.mark.asyncio
async def test_length_finish_without_citations_raises_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_id = uuid.uuid4()
    chunk = SimpleNamespace(
        id=chunk_id,
        text="The warranty period is 24 months.",
        token_count=10,
        page_number=1,
    )
    retrieved = [
        SimpleNamespace(
            chunk=chunk,
            document_id=uuid.uuid4(),
            document_title="Manual",
            score=1.0,
            source="keyword",
        )
    ]

    async def _fake_resolve(*_a, **_k):
        return [uuid.uuid4()]

    async def _fake_retrieve(*_a, **_k):
        return retrieved

    monkeypatch.setattr("lesspaper_ngl.ai.rag.resolve_scope_document_ids", _fake_resolve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.hybrid_retrieve", _fake_retrieve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.assert_ai_quota", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.record_usage", AsyncMock())
    monkeypatch.setattr(
        "lesspaper_ngl.ai.rag.PrivacyGate.assert_can_qa",
        lambda self: None,
    )

    provider = SimpleNamespace(
        name="local",
        context_window=None,
        chat_model="mock",
        is_local=True,
    )
    adapter = _FakeAdapter(
        ChatResult(
            content="The warranty is twenty-four months but I ran out of space",
            model="mock",
            input_tokens=100,
            output_tokens=1024,
            finish_reason="length",
        )
    )

    with pytest.raises(ValidationError, match="output tokens") as excinfo:
        await ask(
            AsyncMock(),
            question="What is the warranty period?",
            settings=_lightweight_settings(),  # type: ignore[arg-type]
            chat_provider=provider,  # type: ignore[arg-type]
            chat_adapter=adapter,  # type: ignore[arg-type]
            chat_model="mock",
            scope=_library_scope(),  # type: ignore[arg-type]
            owner_id=uuid.uuid4(),
        )
    assert OUTPUT_TRUNCATED_MESSAGE in str(excinfo.value.message)


@pytest.mark.asyncio
async def test_numeric_passage_citations_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Models often emit [1] for Passage 1; that must not be treated as no evidence."""
    from lesspaper_ngl.ai.rag import expand_numeric_passage_citations, parse_citations

    chunk_id = uuid.uuid4()
    chunk = SimpleNamespace(
        id=chunk_id,
        text="Make the cue invisible and the good habit obvious.",
        token_count=10,
        page_number=22,
    )
    retrieved = [
        SimpleNamespace(
            chunk=chunk,
            document_id=uuid.uuid4(),
            document_title="Atomic Habits",
            score=1.0,
            source="semantic",
        )
    ]
    expanded = expand_numeric_passage_citations(
        "Swap habits using the four laws [1].",
        retrieved,  # type: ignore[arg-type]
    )
    assert f"[chunk:{chunk_id}]" in expanded
    citations = parse_citations(
        expanded,
        {chunk_id: retrieved[0]},  # type: ignore[arg-type]
    )
    assert len(citations) == 1
    assert citations[0].chunk_id == chunk_id

    async def _fake_resolve(*_a, **_k):
        return [uuid.uuid4()]

    async def _fake_retrieve(*_a, **_k):
        return retrieved

    monkeypatch.setattr("lesspaper_ngl.ai.rag.resolve_scope_document_ids", _fake_resolve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.hybrid_retrieve", _fake_retrieve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.assert_ai_quota", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.record_usage", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.PrivacyGate.assert_can_qa", lambda self: None)

    provider = SimpleNamespace(
        name="local",
        context_window=None,
        chat_model="mock",
        is_local=True,
    )
    adapter = _FakeAdapter(
        ChatResult(
            content="Use the four laws to swap habits [1].",
            model="mock",
            finish_reason="stop",
        )
    )

    result = await ask(
        AsyncMock(),
        question="How do I swap a bad habit?",
        settings=_lightweight_settings(),  # type: ignore[arg-type]
        chat_provider=provider,  # type: ignore[arg-type]
        chat_adapter=adapter,  # type: ignore[arg-type]
        chat_model="mock",
        scope=_library_scope(),  # type: ignore[arg-type]
        owner_id=uuid.uuid4(),
    )
    assert isinstance(result, AskResult)
    assert result.insufficient_evidence is False
    assert len(result.citations) == 1


@pytest.mark.asyncio
async def test_complete_answer_without_citations_is_insufficient_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_id = uuid.uuid4()
    chunk = SimpleNamespace(
        id=chunk_id,
        text="The warranty period is 24 months.",
        token_count=10,
        page_number=1,
    )
    retrieved = [
        SimpleNamespace(
            chunk=chunk,
            document_id=uuid.uuid4(),
            document_title="Manual",
            score=1.0,
            source="keyword",
        )
    ]

    async def _fake_resolve(*_a, **_k):
        return [uuid.uuid4()]

    async def _fake_retrieve(*_a, **_k):
        return retrieved

    monkeypatch.setattr("lesspaper_ngl.ai.rag.resolve_scope_document_ids", _fake_resolve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.hybrid_retrieve", _fake_retrieve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.assert_ai_quota", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.record_usage", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.PrivacyGate.assert_can_qa", lambda self: None)

    provider = SimpleNamespace(
        name="local",
        context_window=None,
        chat_model="mock",
        is_local=True,
    )
    adapter = _FakeAdapter(
        ChatResult(
            content="I think the warranty is long but will not cite anything.",
            model="mock",
            finish_reason="stop",
        )
    )

    result = await ask(
        AsyncMock(),
        question="What is the warranty period?",
        settings=_lightweight_settings(),  # type: ignore[arg-type]
        chat_provider=provider,  # type: ignore[arg-type]
        chat_adapter=adapter,  # type: ignore[arg-type]
        chat_model="mock",
        scope=_library_scope(),  # type: ignore[arg-type]
        owner_id=uuid.uuid4(),
    )
    assert isinstance(result, AskResult)
    assert result.insufficient_evidence is True


@pytest.mark.asyncio
async def test_length_finish_with_early_citations_raises_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_id = uuid.uuid4()
    chunk = SimpleNamespace(
        id=chunk_id,
        text="Awareness is the first step to changing habits.",
        token_count=10,
        page_number=1,
    )
    retrieved = [
        SimpleNamespace(
            chunk=chunk,
            document_id=uuid.uuid4(),
            document_title="Atomic Habits",
            score=1.0,
            source="keyword",
        )
    ]

    async def _fake_resolve(*_a, **_k):
        return [uuid.uuid4()]

    async def _fake_retrieve(*_a, **_k):
        return retrieved

    monkeypatch.setattr("lesspaper_ngl.ai.rag.resolve_scope_document_ids", _fake_resolve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.hybrid_retrieve", _fake_retrieve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.assert_ai_quota", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.record_usage", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.PrivacyGate.assert_can_qa", lambda self: None)

    provider = SimpleNamespace(
        name="local",
        context_window=None,
        chat_model="mock",
        is_local=True,
    )
    adapter = _FakeAdapter(
        ChatResult(
            content=(
                f"Start with awareness [chunk:{chunk_id}]. "
                "Methods include being aware of cues that trigger habits "
                f"[chunk:{str(chunk_id)[:20]}"
            ),
            model="mock",
            input_tokens=100,
            output_tokens=2048,
            finish_reason="length",
        )
    )

    with pytest.raises(ValidationError, match="output tokens"):
        await ask(
            AsyncMock(),
            question="How do I stop bad habits?",
            settings=_lightweight_settings(),  # type: ignore[arg-type]
            chat_provider=provider,  # type: ignore[arg-type]
            chat_adapter=adapter,  # type: ignore[arg-type]
            chat_model="mock",
            scope=_library_scope(),  # type: ignore[arg-type]
            owner_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_incomplete_trailing_citation_raises_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_id = uuid.uuid4()
    chunk = SimpleNamespace(
        id=chunk_id,
        text="Make good habits obvious, attractive, easy, and satisfying.",
        token_count=10,
        page_number=2,
    )
    retrieved = [
        SimpleNamespace(
            chunk=chunk,
            document_id=uuid.uuid4(),
            document_title="Atomic Habits",
            score=1.0,
            source="keyword",
        )
    ]

    async def _fake_resolve(*_a, **_k):
        return [uuid.uuid4()]

    async def _fake_retrieve(*_a, **_k):
        return retrieved

    monkeypatch.setattr("lesspaper_ngl.ai.rag.resolve_scope_document_ids", _fake_resolve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.hybrid_retrieve", _fake_retrieve)
    monkeypatch.setattr("lesspaper_ngl.ai.rag.assert_ai_quota", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.record_usage", AsyncMock())
    monkeypatch.setattr("lesspaper_ngl.ai.rag.PrivacyGate.assert_can_qa", lambda self: None)

    provider = SimpleNamespace(
        name="local",
        context_window=None,
        chat_model="mock",
        is_local=True,
    )
    # finish_reason may be missing/stop while text still ends mid-citation.
    adapter = _FakeAdapter(
        ChatResult(
            content=(
                f"Good habits use the four laws [chunk:{chunk_id}]. "
                "Bad habits invert them [chunk:ad8609a3-a7f7-46c9-90c1-f26"
            ),
            model="mock",
            finish_reason="stop",
        )
    )

    with pytest.raises(ValidationError, match="output tokens"):
        await ask(
            AsyncMock(),
            question="How do I create good habits?",
            settings=_lightweight_settings(),  # type: ignore[arg-type]
            chat_provider=provider,  # type: ignore[arg-type]
            chat_adapter=adapter,  # type: ignore[arg-type]
            chat_model="mock",
            scope=_library_scope(),  # type: ignore[arg-type]
            owner_id=uuid.uuid4(),
        )
