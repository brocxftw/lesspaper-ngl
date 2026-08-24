# Document lifecycle

A **Document** is the owned file record: content-addressed original, metadata, processing flags, pages, and chunks. This page traces states from ingest to purge.

---

## Status models (do not invent a second one)

lesspaper-ngl uses **several complementary fields**, not a single state machine:

| Field / derived | Where | Meaning |
|-----------------|-------|---------|
| `inbox` boolean | DB | Still in the Inbox queue |
| `inbox_status` | Derived in API (`compute_inbox_status`) | `preparing` \| `ready` \| `needs_review` \| `failed` while `inbox=true` |
| `processing_status` | DB enum | `pending` \| `processing` \| `ready` \| `failed` \| `partial` |
| Flags | DB | `text_extracted`, `ocr_completed`, `document_indexed`, `has_embeddings`, `needs_review` |
| Retrieval readiness | **UI-derived** | Preparing / needs review / ready to process / indexing / embedding / keyword ready / semantic ready / failed / partial |

**Inbox Ready** means filing can proceed. It does **not** mean keyword-ready or semantic-ready.

---

## 1. Upload

`POST /api/documents/upload` → `ingest_bytes`.

- MIME allow-list and size limit (`MAX_UPLOAD_SIZE_MB`).
- SHA-256 checksum. Per-owner unique on **active** documents.
- `on_duplicate=error` → HTTP 409; `skip` → 200 without a second row.
- If only a **trashed** duplicate exists, it is permanently deleted and ingest proceeds (new document id).
- Bytes written under `/documents/originals/{aa}/{checksum}.{ext}`. Logical folder is metadata only.

Default folder is system Inbox (`inbox=true`). Optional `relative_path` without `folder_id` keeps the document in Inbox and stores **pending folder path**. Optional `folder_id` files into that library folder immediately (`inbox` follows whether that folder is Inbox).

Jobs enqueued: **text_extraction**, **thumbnail**.

---

## 2. Consume

Worker lists `/consume`, waits for file stability, then `process_consume_file`.

- Owner: `CONSUME_OWNER_USERNAME` or earliest active admin.
- Flat file → Inbox (no relative path).
- Nested path (e.g. `Finance/a.pdf`) → Inbox + pending folder path `Finance` (**Confirmed** in `ingest_bytes`). Process later creates folders under **Documents root**.
- Duplicates skipped (`on_duplicate=skip`); source file removed.
- After successful ingest and checksum verify, source file is deleted.

---

## 3. Text extraction and OCR (preflight)

**text_extraction:** native PDF text (PyMuPDF), DOCX, TXT/MD, images via PaddleOCR inline. Writes `document_pages`, `extracted_text`, refreshes FTS. Sets `processing_status=processing`.

**OCR job:** dedicated pass for thin/scanned PDFs when `OCR_ENABLED`. Page progress committed for UI polling (`ocr_pages_done` / `ocr_pages_total`).

**thumbnail:** derived JPEG thumbnail + preview on disk. Does **not** block Inbox “preflight complete” (`PREFLIGHT_JOB_TYPES` excludes thumbnail).

Keyword FTS can already match page/document text after this stage — **including Inbox documents**. That is not the same as RAG indexing.

---

## 4. Optional AI filing suggestions

If `auto_tagging`, indexing-role provider assigned and **probe=available**, privacy allows Q&A, and extracted text is long enough: enqueue **metadata_suggestion**.

Suggestions are rows on `ai_suggestions` (`pending` / `accepted` / `rejected`). They are **not** canonical metadata until accepted (or Process uses pending path the human confirmed).

Terminal failure of this job is **soft**: document can still become Inbox-ready for manual filing.

---

## 5. Inbox

While `inbox=true`:

| `inbox_status` | Typical cause |
|----------------|---------------|
| preparing | `pending` or `processing` |
| needs_review | No filing target, or `needs_review` |
| ready | Preflight done and target present (pending path or already in a non-Inbox folder) |
| failed | `processing_status=failed` |

Human actions: edit metadata, accept/reject suggestions, set folder/tags/type/correspondent, **Process**, retry preflight/OCR/suggestions, remove from queue (permanent delete of this ingest).

---

## 6. Process

`POST /api/documents/process` → `process_inbox_documents`.

- Skips not-in-inbox, failed preflight, still preparing, Inbox folder with no path.
- Materializes pending path under Documents **root**.
- Sets `inbox=false`, clears `needs_review`.
- Enqueues **INDEXING** if not already `document_indexed`.

Process is the **explicit gate to final chunk indexing for Inbox documents**. It is not “OCR finished”.

---

## 7. Indexing vs embedding

**INDEXING (job):** split page text into `document_chunks` (token-safe chunker). Sets `document_indexed=true`. Does **not** require an AI provider. Then may enqueue:

- **EMBEDDING** if embedding assignment exists and provider probe is available.
- **SUMMARY** if `auto_enrichment` and indexing-role model reachable.

**EMBEDDING (job):** embed **chunk.text** (the indexed passage), pad to 3072 dims, store provider/model/dimension. Updates `has_embeddings`, per-chunk `embedding_status`.

Library documents that never went through Inbox can receive INDEXING from `mark_preflight_ready` after preflight (**Confirmed** exception to “Process always indexes”).

---

## 8. Retrieval readiness (UI)

Computed in `frontend/src/features/documents/retrievalReadiness.ts` from flags — not a DB column.

Ask-on-document UI treats `document_indexed || has_embeddings` as ask-capable.

---

## 9. Archive vs Trash vs Purge

- **Archive:** `is_archived` filter flag. Not delete.
- **Trash:** `is_trashed`, `trashed_at`, optional `trashed_from_folder_id`. Soft-delete. Jobs for trashed docs cancelled/skipped.
- **Restore:** returns to previous folder when possible.
- **Purge / empty / retention:** hard-delete rows; blob removed if no other document shares `storage_key`. Worker purge interval `TRASH_PURGE_INTERVAL_SECONDS`; retention `TRASH_RETENTION_DAYS`.

`DELETE /api/documents/{id}` permanently deletes (not merely trash) — used for remove-from-queue and explicit destroy.

---

## 10. Reprocess and invalidation

| Action | Effect |
|--------|--------|
| Retry preflight | Re-run extract/OCR path; **invalidates** chunks/embeddings/summary |
| Retry OCR | OCR again; invalidates retrieval artefacts |
| Reprocess embeddings | Re-embed existing chunks (or re-queue) |
| Reprocess suggestions | New metadata_suggestion job |

`invalidate_retrieval_artifacts` deletes chunks and clears index/embedding/summary fields so stale RAG artefacts are not queried.

---

## 11. Duplicate handling recap

Checksum is content identity. One blob can back one active document per owner. Logical folder moves never copy or relocate that blob.
