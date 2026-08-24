# Search and retrieval

**Retrieval** finds evidence. It must not call the chat model. **Ask** is a separate capability that *uses* retrieval.

---

## Browse vs evidence search

| Mode | UI | API | Query |
|------|----|-----|-------|
| **Browse** | Documents list/grid, empty search box | `GET /api/documents` | Empty `q`; folder/view/filters |
| **Evidence search** | Documents header or `/search` with text | `POST /api/search` | Non-empty `query` |

Documents workspace switches on `state.q.trim()` (`useDocumentsLibraryState`).

---

## Keyword / semantic / hybrid

| Requested `mode` | Mechanism | Needs embeddings? |
|------------------|-----------|-------------------|
| `keyword` | PostgreSQL FTS on document + page vectors; title/notes/tags contribute at document level | No |
| `semantic` | Embed **query**; cosine distance on chunk vectors in **active embedding space** | Yes |
| `hybrid` | Keyword page hits + semantic chunk hits fused with **RRF** (k=60) | Preferred; see fallback |

**Effective mode:** if hybrid/semantic cannot obtain a query embedding, lesspaper-ngl sets `effective_mode=keyword` (**Confirmed**).

**Semantic coverage:** `embedded_documents` vs `searchable_documents`; `partial` when some searchable docs lack embeddings.

**Snippets / hits / matches:** a **search hit** is a document with score + snippet; nested **matches** have kind `document` \| `page` \| `chunk`.

---

## Filters and scope

`DocumentSearchFilters`: folder(s), descendants, tags, type, correspondent, MIME, archive, inbox, dates, `document_indexed`, `has_embeddings`, `unprocessed`.

Folder-scoped search can be one folder, explicit `folder_ids`, or descendants.

---

## Retrieval readiness vs search

Inbox/preflight documents can appear in **keyword** results because page FTS is updated during extraction. They may not be **Ask-ready** until indexed.

Semantic search only sees chunks that have embeddings in the current provider/model/dimension.

---

## Implementation

`folium.search.fts`, `semantic`, `hybrid`, `filters`, `resolve` (Ask-over-search snapshot → document IDs).
