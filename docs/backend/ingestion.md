# Ingestion

Preparing evidence: get bytes into lesspaper-ngl, extract text, optionally suggest filing, then human **Process**.

---

## Paths into the system

```text
Browser upload  →  POST /api/documents/upload  →  ingest_bytes
Consume folder  →  worker process_consume_file →  ingest_path → ingest_bytes
```

Both share checksum, MIME, quota, and job enqueue behaviour.

---

## Non-AI path (always available)

```text
persist original
  → Document row (usually Inbox)
  → text_extraction (+ thumbnail)
  → OCR if scanned PDF and OCR_ENABLED
  → FTS updated
  → Inbox Ready / needs_review
  → Process
  → INDEXING (chunks)
```

No provider required. Keyword search can hit preflight page text before Process.

---

## AI path (optional)

Enabled only when:

- `ai_settings.auto_tagging` (suggestions) or `auto_enrichment` (summary)
- Role assignments exist (`indexing` chat model; `embedding` for vectors)
- Provider `last_probe_status == available`
- `PrivacyGate` allows the operation

```text
… after usable extracted text …
  → metadata_suggestion  → pending AISuggestion rows
  → human accept/edit
  → Process
  → INDEXING
  → EMBEDDING / SUMMARY if configured
```

If the suggestion job fails, Inbox still proceeds to manual filing (**soft-fail**).

---

## Consume details

- Poll interval `CONSUME_POLL_INTERVAL_SECONDS`; stability wait before ingest.
- Nested relative paths → **pending folder path**, not immediate library folders.
- Source file deleted after verified ingest or skipped duplicate.

---

## Implementation

Worker handlers: `folium.workers.processor`. Extract/OCR: `folium.ocr.extractor`, `paddle_engine`. Ingest: `folium.services.documents`.
