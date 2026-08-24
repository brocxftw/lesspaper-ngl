# Repository inventory

**Evidence date:** 2026-08-16  
**Method:** Inspection of active source, Compose files, Alembic migrations, tests, and CI. Existing README, plans, and comments were treated as secondary.

Evidence labels used throughout this corpus: **Confirmed**, **Configuration-dependent**, **Partial**, **Legacy**, **Planned / not implemented**, **Unknown**, **Inference**.

---

## High-level tree

```text
folium/
├── backend/                 Python FastAPI package + Alembic + tests
│   ├── alembic/versions/    Schema migrations 001–011
│   ├── src/lesspaper_ngl/          Application code
│   └── tests/               unit / integration / eval
├── frontend/                Vite + React SPA
│   └── src/                 routes, workspaces, domain UI, API client
├── docker/                  Backend/frontend Dockerfiles, nginx, entrypoint
├── installer/               Whiptail TUI installer, bootstrap, management CLI
├── docs/                    Engineering documentation (this corpus)
├── data/                    Local bind-mount placeholders (not source)
├── .github/workflows/       CI + GHCR/Release publish
├── docker-compose.yml       Runtime stack
├── docker-compose.debug.yml Optional source-mount overlay
├── .env.example             Documented env template
├── ubiquitous-language.md   Product vocabulary
└── README.md                Public front door (derived from docs/)
```

Not architectural source: `notes.md`, `documents-workspace-redesign.plan.md`, `.cursor/`, `docs/ui-ux/LESSPAPER_NGL_UI_UX_AUDIT.md` (secondary; dated 2026-08-10 and stale on Ask conversations).

`scripts/` exists and is empty (**Confirmed**). Project licence: GNU AGPL v3.0 (`LICENSE`) (**Confirmed**).

---

## Architectural boundaries

| Boundary | Role | Evidence |
|----------|------|----------|
| Browser SPA | React UI; talks HTTP to API | `frontend/src/App.tsx`, nginx proxy |
| `web` | nginx serving built SPA + reverse proxy `/api` `/health` | `docker/Dockerfile.frontend`, `docker/nginx.conf` |
| `api` | FastAPI REST, sessions, enqueue jobs | `folium.main:app` |
| `worker` | Claims jobs, consume poll, trash purge, AI probes | `lesspaper-ngl-worker` |
| PostgreSQL + pgvector | Canonical metadata, FTS, vectors, jobs | `pgvector/pgvector:pg17` |
| Host bind mounts | Originals, consume, export, Paddle cache | Compose volumes |
| Optional AI providers | HTTP adapters; not required for health | `folium.ai.*` |

---

## Backend inventory

**Entrypoint:** `folium.main:create_app` / `uvicorn folium.main:app`. Lifespan runs `bootstrap` (storage layout, admin, system folders, AI settings row).

**API modules (all mounted on the app router):**

| Module | Prefix / paths | Capability |
|--------|----------------|------------|
| `health` | `/health`, `/health/database`, `/health/storage` | Liveness / DB / storage writability |
| `auth` | `/api/auth/*` | Login, register, session, CSRF, profile, password reset |
| `users` | `/api/users/*` | Admin users, invites, password-reset approval |
| `folders` | `/api/folders/*` | Folder tree, trash/restore/purge/delete |
| `tags` | `/api/tags`, document-types, correspondents | Classification metadata |
| `documents` | `/api/documents*` | List, upload, metadata, Process, Ask-on-document, download |
| `inbox` | `/api/inbox/*` | Overview metrics and activity |
| `library` | `/api/library/*` | Library stats / reset counters |
| `trash` | `/api/trash/*` | Counts, purge, empty |
| `search` | `POST /api/search` | Evidence search |
| `ask` | `POST /api/ask` | Workspace-scoped Ask (no conversation persist) |
| `jobs` | `/api/jobs*` | List, get, cancel |
| `ai` | `/api/ai/*` | Providers, policy, assignments, suggestions, usage, health |
| `system` | `/api/system/*` | Summary, storage metrics, diagnostics |
| `logs` | `/api/logs*` | Application logs + CSV export |
| `about` | `/api/about` | Build/about metadata |

OpenAPI is FastAPI default (`/docs`, `/openapi.json`). nginx proxies those from `web`.

**Domain services (not a 1:1 file catalogue):** document lifecycle, folders, tags, jobs, quotas, storage, embedding pipeline, chunking, inbox overview, library stats, users, ask conversations, application logs, system info.

**Auth:** Argon2 passwords; hashed session tokens in `sessions`; CSRF header `X-CSRF-Token` on mutating requests (`SafeSession`). Owner isolation via `owner_id` on library entities.

**Jobs / worker:** PostgreSQL queue (`SKIP LOCKED`). Types: `text_extraction`, `ocr`, `thumbnail`, `indexing`, `embedding`, `summary`, `metadata_suggestion`. Enum also includes `classification` with **no handler** (**Legacy** / unused).

**AI:** Optional. Privacy gate in application code. Roles: `indexing` (filing/summary chat), `embedding`, `chat`, `vision`. **Confirmed naming trap:** `AIWorkloadRole.INDEXING` is not `JobType.INDEXING`.

**Health vs AI:** `GET /health` returns `ok` + version only. AI probe lives on worker + `/api/ai/health`. Unreachable AI does **not** fail container health (**Confirmed**).

---

## Frontend inventory

**Stack:** React 19, Vite 7, React Router 7, TanStack Query 5, Tailwind CSS 4, Radix primitives (dialog, dropdown, tabs, …), Lucide icons, pdf.js, react-markdown. No `components.json`; UI primitives are vendored under `frontend/src/components/ui/` (shadcn-*style*, not a generated shadcn install).

**Routes (AuthGuard):** `/inbox`, `/documents`, `/search`, `/ask`, `/jobs`, `/trash`, `/settings/*`. Guest: `/login`, `/register`, `/forgot-password`, `/reset-password`. `/` redirects to `/documents`. Legacy `/documents/:id` and `/documents/folder/...` redirect into query-param Documents URLs.

**Settings nav (Confirmed):** Profile, Artificial Intelligence (admin), Library, System (admin), Logs (admin), About. Users live under `/settings/profile/users`. Older README “five workspaces” is stale.

**Persisted preferences:** `folium.sidebarOpen`, `folium.documents.layoutMode`, `folium.documents.recentsCollapsed`.

**API client:** `fetch` to same origin with `credentials: include` and CSRF from cookie `folium_csrf` (hard-coded name — **Configuration-dependent** mismatch if `CSRF_COOKIE_NAME` is changed).

---

## Database inventory

Migrations: `001_initial` … `011_ask_conversations`. ORM in `folium.models` matches these tables (**Confirmed** by reading models + latest migrations).

Core tables: `users`, `sessions`, `invites`, `password_reset_requests`, `folders`, `tags`, `document_types`, `correspondents`, `documents`, `document_tags`, `document_pages`, `document_chunks` (pgvector `Vector(3072)`), `jobs`, `ai_providers`, `ai_model_assignments`, `ai_settings`, `ai_usage`, `ai_suggestions`, `ask_conversations`, `ask_messages`, `app_settings`, `library_activity_counters`, `application_logs`.

Ownership: library entities keyed by `owner_id`. Unique `(owner_id, checksum)` on documents. System folders unique per owner (`root` / `inbox` / `trash`).

---

## Runtime / Docker inventory

| Service | Image | Built or pulled |
|---------|-------|-----------------|
| `db` | `pgvector/pgvector:pg17` | Pulled |
| `api` | `ghcr.io/brocxftw/lesspaper-ngl-backend` | Pulled (public); built via `compose.dev.yaml` |
| `worker` | same backend image, `command: lesspaper-ngl-worker` | Same as api |
| `web` | `ghcr.io/brocxftw/lesspaper-ngl-web` | Pulled (public); built via `compose.dev.yaml` |

Public Compose uses `image:` only. GHCR publish is `.github/workflows/publish-images.yml` on `v*` tags. Postgres is not published on the host in public Compose; `5433` is the development overlay. Extra GIDs belong in an override file, not the public Compose.

---

## Testing and CI

**Backend:** pytest unit + integration under `backend/tests/`. OCR extra not installed in CI (engine mocked). Marker `live_ai` for optional real endpoints.

**Frontend:** Vitest (`npm test`) + `tsc -b && vite build`. No Playwright/e2e suite in-repo.

**CI (`.github/workflows/ci.yml`):** backend ruff (`|| true` — not gating), pytest; frontend test+build; `docker compose config`. No image build/publish, no release workflow.

---

## Existing documentation (secondary)

| Artifact | Status |
|----------|--------|
| Root `README.md` (pre-rewrite) | Useful but stale on Settings, Ask multi-turn, AI profile token numbers, consume nested paths |
| `ubiquitous-language.md` | Canonical vocabulary; some entries lagged code (Ask conversations) |
| `docs/ui-ux/LESSPAPER_NGL_UI_UX_AUDIT.md` | UI reverse-engineering 2026-08-10; Ask described as single-turn only |
| `backend/README.md` | Pointer only |
| `backend/pyproject.toml` description | Says “AI-native” — contradicts product principle |

---

## AI-optional principle — audit result

**Mostly satisfied, with documented exceptions.**

Works without any AI provider (**Confirmed**): upload/consume, local OCR/text extract, Inbox/Process, folders/tags, FTS keyword search, Jobs, Trash, users, quotas (storage).

Requires AI when used: Ask lesspaper-ngl (chat assignment), embeddings/semantic/hybrid, filing suggestions (`auto_tagging` + indexing-role model), summaries (`auto_enrichment`).

Exceptions / naming:

1. Package metadata and `__init__` still say “AI-native”.
2. `AIWorkloadRole.INDEXING` is a chat-like role for filing/summary, not chunk indexing.
3. Search `hybrid`/`semantic` will call the embedding provider if assigned (retrieval AI, not chat).
4. Worker periodically probes assigned providers; failure does not mark lesspaper-ngl unhealthy.
