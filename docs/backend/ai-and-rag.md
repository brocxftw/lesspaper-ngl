# AI and RAG

AI is optional. Core DMS and keyword search do not require providers. This page describes what **is** implemented.

---

## Provider roles

| Role (`AIWorkloadRole`) | Used for |
|-------------------------|----------|
| `chat` | Workspace Ask + (legacy fallback) |
| `embedding` | Chunk embeddings + query embedding for search/Ask |
| `indexing` | Filing suggestions + document **summary** (chat completions, not JobType.INDEXING) |
| `vision` | Reserved assignment; filing/Ask paths audited here do not require vision |

Kinds: `openai_compatible`, `openai`, `openrouter`, `ollama` (OpenAI-compatible adapter), `anthropic`, `gemini`.

Secrets encrypted at rest; URLs validated (`folium.ai.url_validation`).

---

## Filing suggestions

When auto-tagging and the indexing-role model is healthy, the worker samples document text, ranks folder/tag candidates, and asks the model for title, folder path, tags, type, correspondent, `needs_review`.

Results are **AISuggestion** rows until accepted. Canonical metadata changes only via accept or human edits / Process.

---

## Embeddings

**What is embedded:** `DocumentChunk.text` (token-chunked page passages), plus the **search/Ask query** string when semantic retrieval runs.

Not embedded: raw PDFs, thumbnails, or whole-library dumps.

Padding: vectors stored in 3072-d columns; `embedding_dimension` is the true size. Active space: `ai_settings.active_embedding_*`.

Privacy: `PrivacyGate.assert_can_embed`.

---

## Ask AI

```text
question
  → privacy + confirm_remote
  → resolve scope document IDs
  → hybrid_retrieve (chunks, profile.retrieved_chunks, token budget)
  → optional conversation history (document Ask only)
  → chat completion (citation instructions)
  → validate citations against retrieved chunk IDs
  → insufficient_evidence if no chunks / model says so / empty scope
```

**Workspace Ask** (`POST /api/ask`): scopes `library`, `folder`, `folder_tree`, `documents`, `document`, `search` (typed snapshot preferred). **No persisted messages.**

**Document Ask**: persisted conversation; history truncated to `conversation_history_tokens`. UI supports new/clear thread. **Not** token-streamed.

Bare `search` scope without snapshot can fall back to FTS title/query on `search_query` inside `resolve_scope_document_ids` (**Confirmed** narrower path than snapshot resolution).

Citations must refer to retrieved chunks (`[chunk:<uuid>]`). Unvalidated IDs are dropped. Insufficient evidence uses a fixed answer string (document Ask UI may rewrite copy).

---

## Profiles and context

Presets (**Confirmed** in `folium.ai.profiles`; README historically understated lightweight output):

| Profile | retrieved_chunks | max_context | max_output |
|---------|------------------|-------------|------------|
| lightweight | 3 | 8 000 | 2 048 |
| balanced | 8 | 16 000 | 3 072 |
| quality | 16 | 32 000 | 4 096 |
| custom | from `ai_settings` | | |

Effective context = min(profile, provider `context_window`) minus safety margin. `semantic_min_score` optionally floors semantic hits.

---

## Fallback

- No chat provider → Ask validation error (not a library-wide health failure).
- No embeddings → Ask retrieval is keyword/FTS hybrid path inside `hybrid_retrieve` when embed adapter missing (**Confirmed** in rag retrieve — keyword-only chunks).
- Remote blocked → `PrivacyViolationError`.

---

## Principle check

lesspaper-ngl **can** run with all providers unset: ingest, OCR, Inbox, Process, keyword search, organisation. Ask, semantic search, suggestions, and summaries will not run. That matches “document management first” with the naming exceptions listed in the [inventory](../audit/repository-inventory.md).
