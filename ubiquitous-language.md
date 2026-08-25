# lesspaper-ngl ubiquitous language

Shared vocabulary for product, design, engineering, and operations.

Use these terms consistently in UI copy, API schemas, tickets, and docs. Prefer the **canonical name** in speech and writing; list **aliases** only when they already appear in code or UI.

> Document management first. AI is an enhancement, not infrastructure.

---

## How to read this dictionary

| Field | Meaning |
|-------|---------|
| **Canonical** | Preferred spoken/written term |
| **Also** | Code identifiers, UI labels, or historical aliases |
| **Means** | The lesspaper-ngl meaning (not the everyday English one) |
| **Not** | Common confusion to avoid |

Terms marked *planned* are intentionally absent from the product until schema/API work is approved.

---

## 1. Product & philosophy

### lesspaper-ngl
**Also:** Folium (former product name)
**Means:** Self-hosted, AI-optional document management for private deployments (homelab, NAS-backed Docker) — for people who want less paper, ngl. Organisation and evidence come first; AI is optional enhancement. Folium has been renamed to lesspaper-ngl.

### Library
**Also:** entire library, documents corpus  
**Means:** An owner’s full set of non-trashed documents used for browse and Ask scope `library`.  
**Not:** The physical NFS share or Docker volume alone — those are *storage*.

### Ingestion
**Also:** upload, consume ingest  
**Means:** Preparing and organising evidence: upload or consume → text/OCR → optional filing suggestions → human Process.  
**Not:** Retrieval or Ask.

### Retrieval
**Also:** evidence search, search  
**Means:** Finding evidence with keyword, semantic, or hybrid search — without calling a chat model.  
**Not:** Ask / generation.

### Ask AI
**Also:** Ask, RAG, Q&A, document ask  
**Means:** User-triggered reasoning over retrieved evidence with validated citations. Workspace Ask (`POST /api/ask`) is one request → one answer with no persisted thread. Document Ask persists a conversation (one per owner+document) and may send prior turns within the history token budget. Streaming is not implemented.  
**Not:** Automatic background summarisation or silent LLM calls from search.

### Logical folder
**Also:** folder (metadata)  
**Means:** Organisational tree node in the database. Moving a document updates metadata only; originals stay content-addressed on disk.  
**Not:** A physical directory move of the stored blob.

### Content-addressed storage
**Also:** checksum storage, originals  
**Means:** Physical files keyed by content hash so one blob serves many metadata placements / duplicates-by-path.

---

## 2. People, tenancy & access

### Owner
**Also:** `owner_id`  
**Means:** The user who owns folders, tags, documents, search hits, and Ask scopes. All library operations are owner-isolated.

### User
**Also:** account  
**Means:** Login identity with display name, admin/active flags, and optional quotas.

### Admin
**Also:** `is_admin`  
**Means:** Can manage users, storage settings, AI providers/policy, and password resets.

### Session
**Means:** Server-side cookie session (cookie name default `folium_session`; CSRF cookie `folium_csrf` — intentional persistence). State-changing API calls require a **CSRF token**.

### Invite
**Means:** Admin-created registration token, optionally carrying default quotas.

### Storage quota
**Also:** `storage_quota_bytes`  
**Means:** Per-user maximum stored bytes (`null` = unlimited).

### AI monthly request quota
**Also:** `ai_monthly_request_quota`  
**Means:** Cap on counted AI operations per calendar month for that user.

### Usage
**Means:** Current consumption (storage used, AI requests this month) versus quotas.

---

## 3. Library organisation

### Document
**Also:** doc  
**Means:** Owned file record: original blob reference, metadata, processing flags, pages, and chunks.

### Folder
**Also:** normal folder  
**Means:** Nested organisational node under the Documents root (`FolderKind.normal`).

### Folder kind
**Also:** `root` \| `inbox` \| `trash` \| `normal`  
**Means:** Distinguishes system folders (one root, inbox, trash per owner) from user folders.

### Documents root
**Also:** root folder, `FolderKind.root`  
**Means:** System parent of the library tree. Consume nested paths are created under this root — not under Inbox.

### Path cache
**Also:** `path_cache`  
**Means:** Cached human-readable folder path (e.g. `Job Hunt / JD / HAVI`).

### Tag
**Means:** Cross-cutting label (name, colour, slug) many-to-many with documents.

### Document type
**Also:** Type  
**Means:** Named classification entity (invoice, statement, job description, …).

### Correspondent
**Means:** Named person or organisation associated with the document.

### Title / Original filename / Notes / Language
**Means:** Core editable and ingest metadata fields on a document.

### Custom fields
**Also:** `custom_fields`  
**Means:** Extensible JSON metadata bag (also used for pending filing path while in Inbox).

### Pending folder path
**Also:** filing target, `pending_folder_path`, inbox folder path  
**Means:** Proposed destination path while the document is still in Inbox; resolved into real folders on Process.

### Created date / Effective date / Added date / Modified date
**Means:**
- **Created date** — business/document date of record  
- **Effective date** — optional secondary business date  
- **Added date** — when lesspaper-ngl ingested the document  
- **Modified date** — last metadata/content change  

### Archive serial
**Means:** Optional unique archive identifier on the document.

### Archived
**Also:** archive / unarchive  
**Means:** Soft archive flag for filtering.  
**Not:** Trash / soft-delete.

### Checksum
**Also:** SHA-256  
**Means:** Content hash of the original. Per-owner duplicate detection uses checksum.

### Duplicate
**Also:** content duplicate  
**Means:** Ingest skipped or rejected because an active document already has the same checksum for that owner.

### Bulk action
**Means:** Multi-document `tag`, `untag`, `move`, `trash`, `restore`, `archive`, or `unarchive`.

### Unprocessed
**Means:** Virtual library view / filter for documents still in the ingestion→indexing path (not yet retrieval-ready as expected).

### Recently added
**Also:** Recent, recent cards  
**Means:** Virtual view and bounded thumbnail cards of newest library documents.

### Starred *(planned)*
**Also:** favourites  
**Means:** Not implemented — no schema or UI until explicitly approved.

---

## 4. Lifecycle: Inbox → Process → Library → Trash

### Inbox
**Also:** system inbox folder, `Document.inbox`  
**Means:** Queue for newly ingested documents that need review and **Process** before final library indexing.  
**Not:** A normal folder you casually file into for finished library docs.

### Inbox status
**Also:** `inbox_status` — `preparing` \| `ready` \| `needs_review` \| `failed`  
**Means:** Derived queue state while `inbox=true`:
- **Preparing** — preflight still running  
- **Ready** (Inbox) — preflight done and filing target present → ready to **Process**  
- **Needs review** — missing target or flagged for confirmation  
- **Failed** — preflight/processing failed  

**Not:** “Ready” here does **not** mean keyword-ready or semantic-ready.

### Needs review
**Also:** `needs_review`, review required  
**Means:** Filing metadata incomplete or explicitly flagged for human confirmation.

### AI suggestion
**Also:** filing suggestion, metadata suggestion  
**Means:** Non-canonical AI proposal for title, folder path, type, correspondent, or tags. Remains a suggestion until accepted.  
**Not:** Canonical library metadata.

### Suggestion status
**Also:** pending \| accepted \| rejected  
**Means:** Lifecycle of an AI suggestion row.

### Process
**Also:** Process gate, Process documents  
**Means:** Explicit human action that leaves Inbox, resolves pending folder path, and queues **final indexing** (and then embeddings when configured).  
**Not:** Automatic completion of OCR.

### Preflight
**Also:** text extraction + OCR (+ optional AI filing)  
**Means:** Jobs that run before Process. Can make keyword/OCR search possible before the document is RAG-indexed.

### Trash
**Also:** soft delete  
**Means:** Soft-deleted documents/folders retained until purge; restorables return to the library.  
**Not:** Archive.

### Purge
**Also:** permanent delete  
**Means:** Hard-delete of trashed items after retention.

### Retention days
**Means:** How long trashed items remain before purge (shown in Trash UI).

---

## 5. Processing pipeline

### Processing status
**Also:** `pending` \| `processing` \| `ready` \| `failed` \| `partial`  
**Means:** Coarse pipeline status on the document record.

### Text extraction
**Also:** extracted text, `text_extracted`  
**Means:** Job that pulls native/embedded text (and may trigger OCR for thin scans / images).

### OCR
**Also:** PaddleOCR, PP-OCRv6, `ocr_completed`  
**Means:** Local optical character recognition for scanned PDFs/images; stores page-aware text.

### Document page
**Also:** page text  
**Means:** Per-page text (+ FTS) used for search snippets and page-aware citations.

### Extracted text
**Means:** Combined full-document text stored on the document.

### Search vector
**Also:** FTS, tsvector  
**Means:** PostgreSQL full-text index on document and/or page text.

### Thumbnail / Preview
**Means:** Derived image assets for cards and light preview. Thumbnails are served; preview JPEGs may exist on disk without a public endpoint.

### Indexing
**Also:** chunk index, final indexing, `document_indexed`  
**Means:** After Process: split page text into **document chunks** for retrieval. Queued by the Process gate (not silently at upload).

### Document chunk
**Also:** chunk  
**Means:** Passage (~500–800 tokens) with page, section, order, and token count — the unit of RAG evidence and embeddings.

### Embedding
**Also:** vector, pgvector, `has_embeddings`  
**Means:** Per-chunk vector produced when an embedding provider is configured and privacy allows. Stored in a fixed Vector(3072) column with padding for smaller models; **embedding dimension** records the true model size.

### Embedding space
**Also:** active embedding provider / model / dimension  
**Means:** The identity of vectors used for semantic queries. Searches filter by provider, model, and dimension.

### Summary
**Also:** AI summary  
**Means:** Direct model summary of a document (not RAG over the library).

### Metadata suggestion (job)
**Means:** Background job that creates AI filing suggestions during preflight when auto-tagging is enabled.

### Reprocess / Retry OCR / Retry preflight
**Means:** Regenerates text/OCR and must invalidate stale FTS, chunks, embeddings, and summaries so retrieval stays consistent.

### Job
**Means:** Database-backed work unit (`queued` → `running` → `completed` \| `failed` \| `cancelled`).

### Job type
**Means:** `text_extraction`, `ocr`, `thumbnail`, `indexing`, `embedding`, `summary`, `metadata_suggestion` (plus reserved `classification`).

### Worker
**Also:** `lesspaper-ngl-worker`  
**Means:** Process that claims and runs jobs (OCR, indexing, embeddings, consume poll, etc.).

### Ingestion history
**Means:** Recent jobs for a document shown in the inspector Overview.  
**Not:** A user Activity / audit feed (unsupported).

---

## 6. Retrieval readiness

### Retrieval readiness
**Also:** readiness badge  
**Means:** UI-derived stage explaining what the document can support for search and Ask. Computed from flags/jobs — not a second contradictory DB status field.

| Readiness | Label | Means |
|-----------|-------|-------|
| `preparing` | Preparing | Text extraction or OCR still running |
| `review_required` | Needs review | Inbox metadata needs confirmation |
| `ready_to_process` | Ready to process | Preflight done; Process from Inbox to index for RAG |
| `indexing` | Indexing | Left Inbox (or library ingest); chunk indexing not finished |
| `embedding` | Embedding | Chunks indexed; embeddings still running |
| `keyword_ready` | Keyword ready | Chunks indexed; embeddings not available yet |
| `semantic_ready` | Semantic ready | Indexed and embedded for hybrid retrieval |
| `failed` | Failed | Processing error |
| `partial` | Partial | Incomplete / mixed stage |

### Ask ready
**Also:** `canAskDocument`  
**Means:** Document has enough indexing (`document_indexed` or `has_embeddings`) to be a sensible Ask target.

### Scope readiness
**Means:** Counts of ask-ready / keyword-ready / semantic-ready / unavailable documents in the current Ask scope (estimated from visible/preview docs when available).

**Trap:** Inbox **Ready** ≠ **Keyword ready** ≠ **Semantic ready**.

---

## 7. Search & evidence

### Browse
**Means:** Empty-query document list (folder/view/filters) via the list API — not the evidence search endpoint.

### Evidence search
**Also:** committed library search  
**Means:** Non-empty query uses hardened keyword/semantic/hybrid retrieval with filters, grouped matches, and accurate totals.

### Keyword search
**Also:** full-text, FTS, mode `keyword`  
**Means:** PostgreSQL full-text over title, notes, tags, extracted and page text (and related fields).

### Semantic search
**Also:** vector search, mode `semantic`  
**Means:** Embed the query and rank by chunk vector similarity in the active embedding space.

### Hybrid search
**Also:** mode `hybrid`  
**Means:** Keyword + semantic results fused (reciprocal rank fusion). Default when semantic is available; may fall back.

### Effective mode
**Means:** Mode actually used when the requested mode cannot run (e.g. semantic requested but embeddings unavailable).

### Semantic coverage
**Also:** partial semantic  
**Means:** How many searchable documents have embeddings vs how many are searchable — surfaces incomplete embedding coverage.

### Semantic available
**Means:** Whether the deployment can run semantic retrieval right now (provider + active embedding identity).

### Search hit
**Means:** Document-level result with score, snippet, and optional nested matches.

### Search match
**Also:** evidence match — kind `document` \| `page` \| `chunk`  
**Means:** Granular evidence underlying a hit (page FTS, chunk semantic/hybrid, etc.).

### Snippet
**Also:** highlight  
**Means:** Short evidence excerpt shown in results (sanitized in UI).

### Document total / Match total
**Means:** Distinct documents vs underlying page/chunk matches for the query.

### Include descendants
**Means:** Folder-scoped list/search includes child folders.

---

## 8. Ask / RAG

### Ask scope
**Also:** scope  
**Means:** Bound of documents for one Ask turn:

| Scope | UI label | Means |
|-------|----------|-------|
| `library` | Entire library | All non-trashed owned documents |
| `folder` | Single folder | Documents directly in one folder |
| `folder_tree` | Folder & subfolders | Folder plus descendants |
| `documents` | Selected documents | Explicit ID list |
| `document` | Current document | One open document |
| `search` | Search results | Documents matching a frozen search snapshot |

### Search scope snapshot
**Also:** typed search scope, `SearchScopeSnapshot`  
**Means:** Frozen evidence-search parameters (query, mode, folder, tags, filters) so Ask-over-results does not silently broaden scope.  
**Not:** A bare `search_query` string alone.

### Citation
**Also:** source  
**Means:** Validated reference returned to the user: document, optional page, chunk id, title, quote. Citation clicks open the viewer at the cited page.

### Passage
**Means:** Retrieved chunk text placed in the model context (also returned for transparency). Citations are the user-facing validated subset.

### Insufficient evidence
**Means:** Canonical outcome when the model/system cannot support an answer from the retrieved scope (`insufficient_evidence`).

### Confirm remote
**Also:** `confirm_remote`, remote confirmation  
**Means:** Explicit user confirmation required before sending content to a non-local provider when warn-before-remote is enabled.

### Single-turn
**Means:** Workspace Ask and the AI drawer: one question → one answer, not stored as a thread.  
**Not:** Document Ask, which **does** persist multi-turn messages (`ask_conversations`). Streaming remains unimplemented.

### Context budget
**Also:** retrieved chunks, max context tokens  
**Means:** Limits from AI profile/policy on how much evidence is packed into an Ask.

---

## 9. Privacy, providers & profiles

### Privacy mode
**Means:** Application-enforced policy:
- **Local only** — document content must not leave for remote AI  
- **Private hybrid** — prefer local; remote only when allowed  
- **Standard** — configured providers subject to allow/block flags  

### Allow remote embeddings / Q&A / vision
**Means:** Fine-grained remote allow switches under privacy mode.

### Warn before remote / Block remote AI
**Means:** UX confirmation gate vs hard block for remote providers.

### AI provider
**Also:** provider  
**Means:** Configured endpoint for chat, embeddings, and/or vision (`openai_compatible`, `ollama`, etc.).

### Is local
**Also:** mark as local  
**Means:** Provider treated as on-host for privacy checks (e.g. LM Studio on LAN).

### No training / Zero retention
**Means:** Provider *policy claims* shown in settings.  
**Not:** lesspaper-ngl guarantees — lesspaper-ngl enforces **privacy mode** in code; provider flags are not proof.

### Chat / Embedding / Vision roles
**Means:** Separate provider assignments on AI settings for each capability.

### AI profile
**Also:** lightweight \| balanced \| quality \| custom  
**Means:** Workload limits (chunks retrieved, token budgets, parallelism).

### AI policy
**Means:** Singleton settings row: privacy mode, profile, provider roles, allow flags, active embedding identity.

### Auto-tagging / Auto-enrichment
**Means:** Policy flags that enable worker AI filing suggestions and related enrichment during preflight.

### Enforcement note
**Means:** Explicit product copy that lesspaper-ngl enforces privacy in application code; provider retention claims are not lesspaper-ngl guarantees.

---

## 10. UI surfaces

### App shell
**Also:** sidebar  
**Means:** Global navigation: Inbox, Documents, Search, Ask, Jobs, Trash, Settings, account.

### Documents workspace
**Also:** Documents page  
**Means:** Library shell — explorer, header search, results (list/grid), modal viewer, AI drawer. Primary surface for find / organise / inspect / understand.

### Documents header
**Means:** Title, dominant retrieval field, mode/coverage, Ask AI, upload.

### Explorer sidebar
**Also:** document explorer  
**Means:** Quick Access + folder tree + tags inside Documents (AppShell trees hidden on this route).

### Quick Access
**Means:** Virtual entries: All documents, Recently added, Unprocessed (+ link to Inbox).

### Library view
**Also:** view tabs — `all` \| `recent` \| `unprocessed`  
**Means:** Which virtual slice of the library is shown.

### Layout mode
**Also:** list \| grid  
**Means:** Persisted results layout preference (`folium.documents.layoutMode`).

### Results toolbar / Bulk toolbar
**Means:** Sort, layout toggle, filter chips; when selected — Move, Tag, Ask, Trash.

### Document viewer
**Also:** viewer modal  
**Means:** Near-full-screen on-demand viewer (PDF/image/text) with page navigation; library state remains underneath.

### Inspector
**Also:** details pane  
**Means:** Overview / Metadata / OCR tabs for the open document.

### Overview
**Means:** Readiness, processing flags, AI summary, ingestion history.

### Metadata
**Also:** Field Data  
**Means:** Editable filing fields (title, folder, tags, type, correspondent, dates, notes).

### OCR tab
**Means:** Page-by-page extracted text and retry actions.  
**Not:** OCR geometry/JSON (unsupported).

### AI drawer
**Also:** AIChatDrawer, Ask panel  
**Means:** Right-side sheet for scoped, single-turn Ask AI with citations.

### Search workspace / Ask workspace
**Means:** Standalone `/search` and `/ask` routes kept for parity with the Documents-integrated workflow.

### Settings workspaces
**Means:** Profile (Users nested for admins), Artificial Intelligence (admin), Library, System (admin), Logs (admin), About. Not a five-item-only IA.

### Filter chips
**Means:** Removable active-filter affordances (query, tags, folder, …).

### Shared with me / Activity *(unsupported)*
**Means:** Intentionally absent — do not invent UI for them.

---

## 11. Storage mounts & ops

### Documents path
**Also:** `/documents`  
**Means:** Host-mounted library storage root (originals, previews, thumbnails, avatars).

### Consume
**Also:** `/consume`, watched folder  
**Means:** Drop zone for automatic ingest. Flat files enter Inbox. Nested relative paths are stored as **pending folder path** on an Inbox document; folders under Documents root are created at **Process**.

### Export
**Also:** `/export`  
**Means:** Export destination mount.

### Backup
**Also:** `.folium` bundle  
**Means:** A versioned recoverable snapshot of lesspaper-ngl canonical state (database dump + referenced originals + avatars).

### Backup repository
**Also:** `/backups`  
**Means:** Mounted filesystem directory where lesspaper-ngl writes backup bundles. lesspaper-ngl does not mount NFS/CIFS itself.

### Restore
**Means:** Replacement of lesspaper-ngl canonical state from a verified compatible backup.  
**Not:** Document import, or Trash restore of a single document.

### Storage key
**Means:** Relative key of the stored original blob under content-addressed originals.

### Storage health
**Also:** ok \| degraded \| unavailable  
**Means:** Writability of documents / consume / export mounts.

### NFS (host-mounted)
**Means:** lesspaper-ngl never mounts NFS itself. The Docker host bind-mounts NFS (or local dirs) into containers. PostgreSQL stays on local Docker volume storage.

---

## 12. Distinctions that must stay sharp

1. **Search retrieves; Ask generates.** Search must never silently invoke the chat model.
2. **Inbox Ready ≠ Keyword ready ≠ Semantic ready.** Process is the gate to final indexing/RAG.
3. **Keyword search can surface Inbox/preflight docs** that are not Ask-ready.
4. **Logical folder move ≠ physical file move.**
5. **Trash ≠ Archive.** Trash is soft-delete with purge; archive is a filter flag.
6. **AI suggestions are non-canonical** until accepted; Process applies filing.
7. **Provider no-training flags ≠ lesspaper-ngl privacy enforcement.**
8. **Ingestion history ≠ Activity feed.** Jobs on a document are technical history, not social activity.
9. **Evidence search (non-empty `q`) ≠ Browse (empty `q`).**
10. **Search-result Ask requires a typed snapshot** (query + mode + filters), not query text alone.

---

## 13. Alphabetical index

Added date · Admin · AI drawer · AI monthly request quota · AI policy · AI profile · AI provider · AI suggestion · Ask AI · Ask ready · Ask scope · Archive serial · Archived · Auto-enrichment · Auto-tagging · Browse · Bulk action · Checksum · Citation · Confirm remote · Consume · Content-addressed storage · Context budget · Correspondent · Created date · CSRF token · Custom fields · Document · Document chunk · Document page · Document total · Document type · Documents path · Documents root · Documents workspace · Duplicate · Effective date · Effective mode · Embedding · Embedding space · Enforcement note · Evidence search · Explorer sidebar · Export · Extracted text · Filter chips · Folder · Folder kind · lesspaper-ngl · Hybrid search · Include descendants · Inbox · Inbox status · Indexing · Ingestion · Ingestion history · Insufficient evidence · Invite · Is local · Job · Job type · Keyword search · Keyword ready · Layout mode · Library · Library view · Logical folder · Match total · Metadata · Metadata suggestion · Modified date · Needs review · NFS · Notes · OCR · OCR tab · Original filename · Overview · Owner · Passage · Path cache · Pending folder path · Preflight · Preview · Privacy mode · Process · Processing status · Purge · Quick Access · Recently added · Retrieval · Retrieval readiness · Reprocess · Retention days · Scope readiness · Search hit · Search match · Search scope snapshot · Search vector · Search workspace · Semantic available · Semantic coverage · Semantic ready · Semantic search · Session · Single-turn · Snippet · Starred *(planned)* · Storage health · Storage key · Storage quota · Suggestion status · Summary · Tag · Text extraction · Thumbnail · Title · Trash · Unprocessed · Usage · User · Viewer · Worker

---

*Source of truth: lesspaper-ngl codebase and product plan. When UI labels and API identifiers differ, keep both in this dictionary and prefer the canonical prose term in conversation.*
