"""Unit tests for Ask conversation helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from lesspaper_ngl.ai.rag import Citation
from lesspaper_ngl.services.ask_conversations import (
    rewrite_answer_with_display_citations,
    select_history_for_model,
    sort_messages_chronologically,
)


def test_rewrite_answer_numbers_citations_in_order() -> None:
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()
    citations = [
        Citation(
            document_id=uuid.uuid4(),
            page_number=1,
            chunk_id=c1,
            title="Doc",
            quote="first",
        ),
        Citation(
            document_id=uuid.uuid4(),
            page_number=2,
            chunk_id=c2,
            title="Doc",
            quote="second",
        ),
    ]
    answer = f"Start [chunk:{c1}] then later [chunk:{c2}] and again [chunk:{c1}]."
    rewritten, snaps = rewrite_answer_with_display_citations(answer, citations)
    assert rewritten == "Start [1] then later [2] and again [1]."
    assert [s["display_number"] for s in snaps] == [1, 2]
    assert snaps[0]["chunk_id"] == str(c1)


def test_rewrite_strips_unknown_chunk_markers() -> None:
    known = uuid.uuid4()
    unknown = uuid.uuid4()
    citations = [
        Citation(
            document_id=uuid.uuid4(),
            page_number=1,
            chunk_id=known,
            title="Doc",
            quote="q",
        )
    ]
    answer = f"Good [chunk:{known}] bad [chunk:{unknown}]."
    rewritten, snaps = rewrite_answer_with_display_citations(answer, citations)
    assert rewritten == "Good [1] bad."
    assert len(snaps) == 1
    assert "chunk:" not in rewritten


def test_rewrite_multi_chunk_group_to_display_numbers() -> None:
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()
    citations = [
        Citation(
            document_id=uuid.uuid4(),
            page_number=1,
            chunk_id=c1,
            title="Doc",
            quote="first",
        ),
        Citation(
            document_id=uuid.uuid4(),
            page_number=2,
            chunk_id=c2,
            title="Doc",
            quote="second",
        ),
    ]
    answer = (
        f"Staf dan Taktik Gred 2 [chunk:{c1}, chunk:{c2}] "
        f"and again [chunk:{c2}, chunk:{c1}]."
    )
    rewritten, _ = rewrite_answer_with_display_citations(answer, citations)
    assert rewritten == "Staf dan Taktik Gred 2 [1][2] and again [2][1]."
    assert "chunk:" not in rewritten


def test_rewrite_collapses_consecutive_duplicate_numbers() -> None:
    from lesspaper_ngl.services.ask_conversations import normalize_display_citation_text

    assert normalize_display_citation_text("Focus on identity [5] [5]. More.") == (
        "Focus on identity [5]. More."
    )
    assert normalize_display_citation_text("loop [1] . Next") == "loop [1]. Next"


def test_sort_messages_user_before_assistant_on_timestamp_tie() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    assistant = SimpleNamespace(
        role="assistant",
        created_at=ts,
        id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )
    user = SimpleNamespace(
        role="user",
        created_at=ts,
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )
    ordered = sort_messages_chronologically([assistant, user])  # type: ignore[arg-type]
    assert [m.role for m in ordered] == ["user", "assistant"]


def test_select_history_prefers_newest_under_budget() -> None:
    messages = [
        SimpleNamespace(role="user", content="a " * 50),
        SimpleNamespace(role="assistant", content="b " * 50),
        SimpleNamespace(role="user", content="latest question"),
    ]
    # Tiny budget should still keep the newest message.
    selected = select_history_for_model(messages, token_budget=8)  # type: ignore[arg-type]
    assert selected
    assert selected[-1].content == "latest question"
    assert selected[-1].role == "user"
