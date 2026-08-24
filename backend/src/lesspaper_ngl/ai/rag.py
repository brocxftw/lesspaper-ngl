"""Evidence-backed retrieval-augmented generation."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

import tiktoken
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.base import AIProviderAdapter, ChatMessage
from lesspaper_ngl.ai.embeddings import pad_embedding
from lesspaper_ngl.ai.privacy import PrivacyGate
from lesspaper_ngl.ai.profiles import compute_budget, effective_context_window, resolve_profile
from lesspaper_ngl.ai.usage import record_usage
from lesspaper_ngl.core.exceptions import InsufficientEvidenceError, ValidationError
from lesspaper_ngl.models import AIProvider, AISettings, Document, DocumentChunk, Folder
from lesspaper_ngl.services import folders as folder_service
from lesspaper_ngl.services.quotas import assert_ai_quota

INSUFFICIENT_EVIDENCE_ANSWER = "Insufficient evidence was found in the selected documents."
OUTPUT_TRUNCATED_MESSAGE = (
    "The model ran out of output tokens before finishing a complete cited answer. "
    "Raise the AI profile output limit, switch to a higher profile, or ask a narrower question."
)

# Trailing incomplete citation marker, e.g. "[chunk:ad8609a3-a7f7-46c9-90c1-f26"
_INCOMPLETE_CITATION_RE = re.compile(
    r"\[chunk:(?:[0-9a-fA-F-]{0,35})?$",
    re.IGNORECASE,
)

_UUID = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# Single marker: [chunk:<uuid>]
CITATION_PATTERN = re.compile(rf"\[chunk:({_UUID})\]", re.IGNORECASE)

# Any chunk:<uuid> occurrence (also covers multi-id groups the model invents).
CHUNK_ID_PATTERN = re.compile(rf"chunk:\s*({_UUID})", re.IGNORECASE)

# Bracket groups with one or more chunk ids, e.g.
# [chunk:uuid] or [chunk:uuid, chunk:uuid]
CHUNK_CITATION_GROUP_PATTERN = re.compile(
    rf"\[\s*chunk:\s*{_UUID}"
    rf"(?:\s*,\s*chunk:\s*{_UUID})*"
    rf"\s*\]",
    re.IGNORECASE,
)

SCOPE_DOCUMENT = "document"
SCOPE_DOCUMENTS = "documents"
SCOPE_FOLDER = "folder"
SCOPE_SUBTREE = "folder_tree"
SCOPE_SEARCH = "search"
SCOPE_LIBRARY = "library"


@dataclass(slots=True)
class Citation:
    document_id: uuid.UUID
    page_number: int | None
    chunk_id: uuid.UUID
    title: str
    quote: str | None = None


@dataclass(slots=True)
class AskResult:
    answer: str
    citations: list[Citation]
    passages: list[Citation]
    provider: str | None
    model: str | None
    insufficient_evidence: bool = False


@dataclass(slots=True)
class RetrievedChunk:
    chunk: DocumentChunk
    document_id: uuid.UUID
    document_title: str
    score: float
    source: str


@dataclass(slots=True)
class RAGScope:
    kind: str
    document_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] = field(default_factory=list)
    folder_id: uuid.UUID | None = None
    search_query: str | None = None


def _encoding() -> tiktoken.Encoding:
    try:
        return tiktoken.get_encoding("cl100k_base")
    except KeyError:
        return tiktoken.get_encoding("gpt2")


def estimate_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def _base_document_query(owner_id: uuid.UUID) -> Select[tuple[Document]]:
    return select(Document).where(
        Document.owner_id == owner_id,
        Document.is_trashed.is_(False),
    )


async def resolve_scope_document_ids(
    session: AsyncSession,
    scope: RAGScope,
    owner_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Resolve a RAG scope to the document IDs that may be queried."""
    match scope.kind:
        case scope_kind if scope_kind == SCOPE_DOCUMENT:
            if scope.document_id is None:
                raise ValidationError("document scope requires document_id.")
            stmt = _base_document_query(owner_id).where(Document.id == scope.document_id)
        case scope_kind if scope_kind == SCOPE_DOCUMENTS:
            if not scope.document_ids:
                raise ValidationError("documents scope requires document_ids.")
            stmt = _base_document_query(owner_id).where(Document.id.in_(scope.document_ids))
        case scope_kind if scope_kind == SCOPE_FOLDER:
            if scope.folder_id is None:
                raise ValidationError("folder scope requires folder_id.")
            folder = await session.get(Folder, scope.folder_id)
            if folder is None or folder.owner_id != owner_id:
                raise ValidationError("Folder not found for folder scope.")
            stmt = _base_document_query(owner_id).where(Document.folder_id == scope.folder_id)
        case scope_kind if scope_kind == SCOPE_SUBTREE:
            if scope.folder_id is None:
                raise ValidationError("folder_tree scope requires folder_id.")
            folder = await session.get(Folder, scope.folder_id)
            if folder is None or folder.owner_id != owner_id:
                raise ValidationError("Folder not found for folder_tree scope.")
            folder_ids = await folder_service.descendant_ids(
                session,
                folder.id,
                owner_id=owner_id,
            )
            stmt = _base_document_query(owner_id).where(Document.folder_id.in_(folder_ids))
        case scope_kind if scope_kind == SCOPE_SEARCH:
            query = (scope.search_query or "").strip()
            if not query:
                raise ValidationError("search scope requires search_query.")
            ts_query = func.plainto_tsquery("english", query)
            stmt = _base_document_query(owner_id).where(
                or_(
                    Document.search_vector.op("@@")(ts_query),
                    Document.title.ilike(f"%{query}%"),
                )
            )
        case scope_kind if scope_kind == SCOPE_LIBRARY:
            stmt = _base_document_query(owner_id)
        case _:
            raise ValidationError(f"Unsupported RAG scope: {scope.kind}")

    documents = await session.scalars(stmt)
    return [document.id for document in documents.all()]


async def _semantic_retrieve(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID],
    limit: int,
    embed_adapter: AIProviderAdapter,
    embedding_model: str | None,
    embedding_provider: str | None,
    embedding_dimension: int | None,
) -> list[RetrievedChunk]:
    embedding_result = await embed_adapter.embed([question], model=embedding_model)
    if not embedding_result.embeddings:
        return []

    query_vector = pad_embedding(embedding_result.embeddings[0])

    distance_expr = DocumentChunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(DocumentChunk, Document.title, distance_expr.label("distance"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(document_ids))
        .where(DocumentChunk.embedding.is_not(None))
        .where(Document.owner_id == owner_id)
        .where(Document.is_trashed.is_(False))
    )

    if embedding_provider:
        stmt = stmt.where(DocumentChunk.embedding_provider == embedding_provider)
    if embedding_model:
        stmt = stmt.where(DocumentChunk.embedding_model == embedding_model)
    if embedding_dimension:
        stmt = stmt.where(DocumentChunk.embedding_dimension == embedding_dimension)

    stmt = stmt.order_by(distance_expr).limit(limit)

    rows = (await session.execute(stmt)).all()
    retrieved: list[RetrievedChunk] = []
    for chunk, title, distance in rows:
        # Cosine similarity in [approx -1, 1]; matches search.semantic scoring.
        score = 1.0 - float(distance)
        retrieved.append(
            RetrievedChunk(
                chunk=chunk,
                document_id=chunk.document_id,
                document_title=title,
                score=score,
                source="semantic",
            )
        )
    return retrieved


async def _keyword_retrieve(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID],
    limit: int,
) -> list[RetrievedChunk]:
    ts_query = func.plainto_tsquery("english", question)
    ts_vector = func.to_tsvector("english", DocumentChunk.text)
    rank_expr = func.ts_rank(ts_vector, ts_query)

    stmt = (
        select(DocumentChunk, Document.title, rank_expr.label("rank"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(document_ids))
        .where(Document.owner_id == owner_id)
        .where(Document.is_trashed.is_(False))
        .where(ts_vector.op("@@")(ts_query))
        .order_by(rank_expr.desc())
        .limit(limit)
    )

    rows = (await session.execute(stmt)).all()
    retrieved: list[RetrievedChunk] = []
    for chunk, title, rank in rows:
        retrieved.append(
            RetrievedChunk(
                chunk=chunk,
                document_id=chunk.document_id,
                document_title=title,
                score=float(rank or 0.0),
                source="keyword",
            )
        )
    return retrieved


def _reciprocal_rank_fusion(
    *ranked_lists: list[RetrievedChunk],
    k: int = 60,
) -> list[RetrievedChunk]:
    scores: dict[uuid.UUID, float] = {}
    merged: dict[uuid.UUID, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item.chunk.id] = scores.get(item.chunk.id, 0.0) + (1.0 / (k + rank))
            merged[item.chunk.id] = item

    ordered_ids = sorted(scores.keys(), key=lambda chunk_id: scores[chunk_id], reverse=True)
    result: list[RetrievedChunk] = []
    for chunk_id in ordered_ids:
        item = merged[chunk_id]
        result.append(
            RetrievedChunk(
                chunk=item.chunk,
                document_id=item.document_id,
                document_title=item.document_title,
                score=scores[chunk_id],
                source=item.source,
            )
        )
    return result


def _fit_chunks_to_budget(
    ranked: list[RetrievedChunk],
    *,
    max_chunks: int,
    token_budget: int,
) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    used_tokens = 0

    for item in ranked:
        if len(selected) >= max_chunks:
            break

        chunk_tokens = item.chunk.token_count or estimate_tokens(item.chunk.text)
        # Account for passage labels / UUID / title framing in the user message.
        overhead = estimate_tokens(
            f"Passage {len(selected) + 1}:\nchunk_id: {item.chunk.id}\n"
            f"document: {item.document_title}\nlocation: page 999\ntext:\n"
        )
        cost = chunk_tokens + overhead
        if used_tokens + cost > token_budget:
            continue

        selected.append(item)
        used_tokens += cost

    return selected


async def hybrid_retrieve(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID],
    max_chunks: int,
    token_budget: int,
    embed_adapter: AIProviderAdapter | None,
    embedding_model: str | None,
    embedding_provider: str | None,
    embedding_dimension: int | None,
    semantic_min_score: float | None = None,
) -> list[RetrievedChunk]:
    """Retrieve top chunks using keyword search and optional semantic search."""
    if not document_ids:
        return []

    candidate_limit = max(max_chunks * 4, max_chunks)

    keyword_hits = await _keyword_retrieve(
        session,
        owner_id=owner_id,
        question=question,
        document_ids=document_ids,
        limit=candidate_limit,
    )

    semantic_hits: list[RetrievedChunk] = []
    if embed_adapter is not None:
        try:
            semantic_hits = await _semantic_retrieve(
                session,
                owner_id=owner_id,
                question=question,
                document_ids=document_ids,
                limit=candidate_limit,
                embed_adapter=embed_adapter,
                embedding_model=embedding_model,
                embedding_provider=embedding_provider,
                embedding_dimension=embedding_dimension,
            )
        except Exception:
            semantic_hits = []

    if semantic_min_score is not None:
        semantic_hits = [item for item in semantic_hits if item.score >= semantic_min_score]

    if semantic_hits and keyword_hits:
        ranked = _reciprocal_rank_fusion(semantic_hits, keyword_hits)
    elif semantic_hits:
        ranked = semantic_hits
    else:
        ranked = keyword_hits

    return _fit_chunks_to_budget(ranked, max_chunks=max_chunks, token_budget=token_budget)


def _ask_system_prompt() -> str:
    return (
        "You are a document assistant for lesspaper-ngl. Answer the user's question using ONLY "
        "the evidence passages below. Do not rely on outside knowledge.\n"
        "When you make a factual claim supported by a passage, cite it inline using "
        "the exact format [chunk:<chunk_id>].\n"
        "Be concise: prefer short paragraphs or brief bullet lists over long essays. "
        "Do not repeat the same citation on every sentence when one citation covers a point.\n"
        "If the passages do not contain enough information to answer confidently, reply "
        "with exactly: INSUFFICIENT_EVIDENCE\n"
        "Never invent citations or chunk IDs."
    )


def _ask_user_framing(question: str) -> str:
    """User message without evidence body — used for budgeting."""
    return (
        "Evidence passages:\n\n\n\n"
        f"Question: {question.strip()}\n\n"
        "Provide a concise answer with inline [chunk:<chunk_id>] citations."
    )


def build_rag_prompt(question: str, chunks: list[RetrievedChunk]) -> tuple[str, list[ChatMessage]]:
    """Build system and user messages requiring chunk citations."""
    evidence_lines: list[str] = []
    for index, item in enumerate(chunks, start=1):
        page = item.chunk.page_number
        page_label = f"page {page}" if page is not None else "page unknown"
        evidence_lines.append(
            "\n".join(
                [
                    f"Passage {index}:",
                    f"chunk_id: {item.chunk.id}",
                    f"document: {item.document_title}",
                    f"location: {page_label}",
                    "text:",
                    item.chunk.text.strip(),
                ]
            )
        )

    evidence_block = "\n\n".join(evidence_lines)
    system_prompt = _ask_system_prompt()
    user_prompt = (
        f"Evidence passages:\n\n{evidence_block}\n\n"
        f"Question: {question.strip()}\n\n"
        "Provide a concise answer with inline [chunk:<chunk_id>] citations."
    )

    return system_prompt, [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]


# Models sometimes cite evidence as [1]/[2] matching "Passage N:" in the prompt
# instead of the required [chunk:<uuid>] form.
_NUMERIC_PASSAGE_CITATION_RE = re.compile(r"\[(\d+)\]")


def expand_numeric_passage_citations(
    answer: str,
    retrieved: list[RetrievedChunk],
) -> str:
    """Map ``[n]`` passage citations to ``[chunk:<uuid>]`` when ``n`` is in range."""
    if not retrieved:
        return answer

    def _replace(match: re.Match[str]) -> str:
        try:
            index = int(match.group(1))
        except ValueError:
            return match.group(0)
        if index < 1 or index > len(retrieved):
            return match.group(0)
        return f"[chunk:{retrieved[index - 1].chunk.id}]"

    return _NUMERIC_PASSAGE_CITATION_RE.sub(_replace, answer)


def parse_citations(answer: str, chunk_map: dict[uuid.UUID, RetrievedChunk]) -> list[Citation]:
    """Extract and validate chunk citations from an model answer."""
    seen: set[uuid.UUID] = set()
    citations: list[Citation] = []

    for match in CHUNK_ID_PATTERN.finditer(answer):
        chunk_id = uuid.UUID(match.group(1))
        if chunk_id in seen:
            continue
        item = chunk_map.get(chunk_id)
        if item is None:
            continue
        seen.add(chunk_id)
        citations.append(
            Citation(
                document_id=item.document_id,
                page_number=item.chunk.page_number,
                chunk_id=item.chunk.id,
                title=item.document_title,
                quote=_truncate_quote(item.chunk.text),
            )
        )

    return citations


def _truncate_quote(text: str, *, max_chars: int = 280) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def passages_from_chunks(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            document_id=item.document_id,
            page_number=item.chunk.page_number,
            chunk_id=item.chunk.id,
            title=item.document_title,
            quote=_truncate_quote(item.chunk.text),
        )
        for item in chunks
    ]


def _answer_indicates_insufficient_evidence(answer: str) -> bool:
    normalized = answer.strip().upper()
    return normalized == "INSUFFICIENT_EVIDENCE" or normalized.startswith("INSUFFICIENT_EVIDENCE")


def _answer_looks_truncated(answer: str, finish_reason: str | None) -> bool:
    """True when the provider stopped for length or the text ends mid-citation."""
    if (finish_reason or "").lower() == "length":
        return True
    stripped = answer.rstrip()
    if _INCOMPLETE_CITATION_RE.search(stripped):
        return True
    # Cut mid-markdown list / sentence is harder to detect; length finish_reason is primary.
    if stripped.endswith("[chunk:") or stripped.endswith("[chunk"):
        return True
    return False


async def ask(
    session: AsyncSession,
    *,
    question: str,
    settings: AISettings,
    chat_provider: AIProvider,
    chat_adapter: AIProviderAdapter,
    chat_model: str | None = None,
    scope: RAGScope,
    owner_id: uuid.UUID,
    embed_adapter: AIProviderAdapter | None = None,
    embedding_model: str | None = None,
    embedding_provider: str | None = None,
    conversation: list[ChatMessage] | None = None,
) -> AskResult:
    """Run an evidence-backed question answering flow over a scoped document set."""
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValidationError("Question must not be empty.")

    PrivacyGate(settings, chat_provider).assert_can_qa()

    profile = resolve_profile(settings)
    document_ids = await resolve_scope_document_ids(session, scope, owner_id)
    if not document_ids:
        return AskResult(
            answer=INSUFFICIENT_EVIDENCE_ANSWER,
            citations=[],
            passages=[],
            provider=chat_provider.name,
            model=chat_model or chat_provider.chat_model,
            insufficient_evidence=True,
        )

    await assert_ai_quota(session, owner_id)
    system_tokens = estimate_tokens(_ask_system_prompt())
    framing_tokens = estimate_tokens(_ask_user_framing(cleaned_question))
    conversation_tokens = 0
    if conversation:
        conversation_tokens = sum(estimate_tokens(message.content) for message in conversation)

    max_context = effective_context_window(
        profile.max_context_tokens,
        chat_provider.context_window,
    )
    budget = compute_budget(
        max_context,
        system_tokens + framing_tokens,
        min(conversation_tokens, profile.conversation_history_tokens),
        profile.max_output_tokens,
    )

    semantic_min_score = settings.semantic_min_score

    retrieved = await hybrid_retrieve(
        session,
        owner_id=owner_id,
        question=cleaned_question,
        document_ids=document_ids,
        max_chunks=profile.retrieved_chunks,
        token_budget=budget.rag_budget,
        embed_adapter=embed_adapter,
        embedding_model=embedding_model or settings.active_embedding_model,
        embedding_provider=embedding_provider or settings.active_embedding_provider,
        embedding_dimension=settings.active_embedding_dimension,
        semantic_min_score=semantic_min_score,
    )

    if not retrieved:
        return AskResult(
            answer=INSUFFICIENT_EVIDENCE_ANSWER,
            citations=[],
            passages=[],
            provider=chat_provider.name,
            model=chat_model or chat_provider.chat_model,
            insufficient_evidence=True,
        )

    chunk_map = {item.chunk.id: item for item in retrieved}
    system_prompt, rag_messages = build_rag_prompt(cleaned_question, retrieved)

    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
    if conversation:
        history_budget = profile.conversation_history_tokens
        used = 0
        for message in conversation:
            message_tokens = estimate_tokens(message.content)
            if used + message_tokens > history_budget:
                break
            messages.append(message)
            used += message_tokens
    messages.extend(rag_messages[1:])

    started = time.perf_counter()
    chat_result = await chat_adapter.chat(
        messages,
        model=chat_model or chat_provider.chat_model,
        max_tokens=profile.max_output_tokens,
        temperature=0.2,
    )
    duration_ms = round((time.perf_counter() - started) * 1000)

    await record_usage(
        session,
        user_id=owner_id,
        provider=chat_provider.name,
        model=chat_result.model,
        operation="qa",
        input_tokens=chat_result.input_tokens,
        output_tokens=chat_result.output_tokens,
        is_local=chat_provider.is_local,
        document_id=scope.document_id,
        duration_ms=duration_ms,
    )

    raw_answer = chat_result.content.strip()
    passages = passages_from_chunks(retrieved)

    if _answer_indicates_insufficient_evidence(raw_answer):
        return AskResult(
            answer=INSUFFICIENT_EVIDENCE_ANSWER,
            citations=[],
            passages=passages,
            provider=chat_provider.name,
            model=chat_result.model,
            insufficient_evidence=True,
        )

    if _answer_looks_truncated(raw_answer, chat_result.finish_reason):
        raise ValidationError(OUTPUT_TRUNCATED_MESSAGE)

    # Accept [n] passage-index citations the model often emits instead of [chunk:uuid].
    answer = expand_numeric_passage_citations(raw_answer, retrieved)
    citations = parse_citations(answer, chunk_map)
    if not citations:
        return AskResult(
            answer=INSUFFICIENT_EVIDENCE_ANSWER,
            citations=[],
            passages=passages,
            provider=chat_provider.name,
            model=chat_result.model,
            insufficient_evidence=True,
        )

    return AskResult(
        answer=answer,
        citations=citations,
        passages=passages,
        provider=chat_provider.name,
        model=chat_result.model,
        insufficient_evidence=False,
    )


async def ask_or_raise(
    session: AsyncSession,
    **kwargs: object,
) -> AskResult:
    """Run ask() and raise InsufficientEvidenceError when evidence is insufficient."""
    result = await ask(session, **kwargs)  # type: ignore[arg-type]
    if result.insufficient_evidence:
        raise InsufficientEvidenceError(result.answer)
    return result
