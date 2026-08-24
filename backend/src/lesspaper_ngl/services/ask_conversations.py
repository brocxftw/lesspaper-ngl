"""Persist one active Ask conversation per owner+document."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lesspaper_ngl.ai.base import ChatMessage
from lesspaper_ngl.ai.rag import (
    CHUNK_CITATION_GROUP_PATTERN,
    CHUNK_ID_PATTERN,
    Citation,
)
from lesspaper_ngl.models import AskConversation, AskMessage
from lesspaper_ngl.services.chunking import estimate_tokens

logger = logging.getLogger(__name__)

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# Prefer user before assistant when timestamps collide (UUIDs are not ordered).
_MESSAGE_ROLE_ORDER = case(
    (AskMessage.role == ROLE_USER, 0),
    else_=1,
)

# Catch malformed / leftover bracketed chunk markers after the main rewrite.
_BRACKETED_CHUNK_LEFTOVER_RE = re.compile(r"\[chunk:[^\]]*\]", re.IGNORECASE)


def rewrite_answer_with_display_citations(
    answer: str,
    citations: list[Citation],
) -> tuple[str, list[dict[str, Any]]]:
    """Replace chunk citation markers with ``[1]…[n]`` using citation order.

    Handles single ``[chunk:<uuid>]`` and multi-id groups such as
    ``[chunk:<uuid>, chunk:<uuid>]``. Unknown markers are stripped so raw
    chunk references never reach the UI.
    """
    id_to_number: dict[uuid.UUID, int] = {}
    snapshots: list[dict[str, Any]] = []
    for index, citation in enumerate(citations, start=1):
        id_to_number[citation.chunk_id] = index
        snapshots.append(
            {
                "display_number": index,
                "chunk_id": str(citation.chunk_id),
                "document_id": str(citation.document_id),
                "page_number": citation.page_number,
                "title": citation.title,
                "quote": citation.quote,
            }
        )

    def _replace_group(match: re.Match[str]) -> str:
        numbers: list[int] = []
        for id_match in CHUNK_ID_PATTERN.finditer(match.group(0)):
            try:
                chunk_id = uuid.UUID(id_match.group(1))
            except ValueError:
                continue
            number = id_to_number.get(chunk_id)
            if number is not None and number not in numbers:
                numbers.append(number)
        if not numbers:
            return ""
        return "".join(f"[{number}]" for number in numbers)

    rewritten = CHUNK_CITATION_GROUP_PATTERN.sub(_replace_group, answer)
    rewritten = strip_raw_chunk_markers(rewritten)
    return normalize_display_citation_text(rewritten), snapshots


def strip_raw_chunk_markers(text: str) -> str:
    """Remove any remaining raw ``chunk:<uuid>`` markers from display text."""
    cleaned = _BRACKETED_CHUNK_LEFTOVER_RE.sub("", text)
    cleaned = CHUNK_ID_PATTERN.sub("", cleaned)
    return cleaned


def normalize_display_citation_text(text: str) -> str:
    """Tidy display citation markers after chunk→number rewrite.

    - Collapse consecutive identical ``[n][n]`` (model often re-cites same chunk).
    - Keep punctuation attached to the citation badge.
    - Clean leftover spaces from stripped unknown markers.
    """
    cleaned = text
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = re.sub(r"\[(\d+)\](?:\s*)\[\1\]", r"[\1]", cleaned)
    cleaned = re.sub(r"\[(\d+)\]\s+([.,;:!?])", r"[\1]\2", cleaned)
    cleaned = re.sub(r"[^\S\n]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()


def select_history_for_model(
    messages: list[AskMessage],
    *,
    token_budget: int,
) -> list[ChatMessage]:
    """Prefer newest turns, then return chronological ChatMessages under budget."""
    if token_budget <= 0 or not messages:
        return []

    selected: list[AskMessage] = []
    used = 0
    for message in reversed(messages):
        tokens = estimate_tokens(message.content)
        if selected and used + tokens > token_budget:
            break
        selected.append(message)
        used += tokens

    selected.reverse()
    return [
        ChatMessage(role=message.role, content=message.content)  # type: ignore[arg-type]
        for message in selected
        if message.role in (ROLE_USER, ROLE_ASSISTANT)
    ]


async def get_or_create_conversation(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
) -> AskConversation:
    existing = await session.scalar(
        select(AskConversation).where(
            AskConversation.owner_id == owner_id,
            AskConversation.document_id == document_id,
        )
    )
    if existing is not None:
        return existing

    conversation = AskConversation(owner_id=owner_id, document_id=document_id)
    session.add(conversation)
    await session.flush()
    return conversation


async def load_conversation_with_messages(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
) -> AskConversation | None:
    return await session.scalar(
        select(AskConversation)
        .where(
            AskConversation.owner_id == owner_id,
            AskConversation.document_id == document_id,
        )
        .options(selectinload(AskConversation.messages))
    )


async def list_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
) -> list[AskMessage]:
    result = await session.scalars(
        select(AskMessage)
        .where(AskMessage.conversation_id == conversation_id)
        .order_by(
            AskMessage.created_at.asc(),
            _MESSAGE_ROLE_ORDER,
            AskMessage.id.asc(),
        )
    )
    return list(result.all())


def sort_messages_chronologically(messages: list[AskMessage]) -> list[AskMessage]:
    """Stable conversation order: time, then user before assistant."""
    return sorted(
        messages,
        key=lambda m: (
            m.created_at,
            0 if m.role == ROLE_USER else 1,
            str(m.id),
        ),
    )

async def append_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
    created_at: datetime | None = None,
) -> AskMessage:
    kwargs: dict[str, Any] = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "citations": citations,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    message = AskMessage(**kwargs)
    session.add(message)
    await session.flush()
    conversation = await session.get(AskConversation, conversation_id)
    if conversation is not None:
        conversation.updated_at = datetime.now(UTC)
    await session.flush()
    return message


async def clear_conversation(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
) -> bool:
    """Delete the active conversation (and messages via CASCADE). Returns True if deleted."""
    conversation = await session.scalar(
        select(AskConversation).where(
            AskConversation.owner_id == owner_id,
            AskConversation.document_id == document_id,
        )
    )
    if conversation is None:
        return False
    await session.delete(conversation)
    await session.flush()
    return True


async def replace_with_new_conversation(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
) -> AskConversation:
    """Drop any existing conversation and create a fresh empty one."""
    await session.execute(
        delete(AskConversation).where(
            AskConversation.owner_id == owner_id,
            AskConversation.document_id == document_id,
        )
    )
    conversation = AskConversation(owner_id=owner_id, document_id=document_id)
    session.add(conversation)
    await session.flush()
    return conversation
