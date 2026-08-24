# Runtime architecture

How lesspaper-ngl processes actually run in the Compose stack versus local development.

---

## Compose services

| Service | Process | Command | Depends on |
|---------|---------|---------|------------|
| `db` | PostgreSQL 17 + pgvector | image default | — |
| `api` | Uvicorn FastAPI | entrypoint → `uvicorn folium.main:app --host 0.0.0.0 --port 8000` | healthy `db`; runs `alembic upgrade head` first |
| `worker` | asyncio worker loop | `lesspaper-ngl-worker` | healthy `db` and healthy `api` |
| `web` | nginx | image default | healthy `api` |

**Confirmed:** `api` and `worker` share `docker/Dockerfile.backend`. The worker does **not** run migrations (entrypoint skips Alembic when argv is `lesspaper-ngl-worker`). Ordering `worker → api healthy` exists so schema is migrated before jobs run.

Worker Compose healthcheck runs `python -m folium.workers.healthcheck` (90s stale window). A background task writes `app_settings.worker_heartbeat` about every 10s. That heartbeat is **not** part of `GET /health`.

---

## Network and ports

| Port (host → container) | Service |
|-------------------------|---------|
| `9398 → 80` | `web` (primary UI) |
| `9099 → 8000` | `api` (optional direct OpenAPI / MCP) |
| `5433 → 5432` | `db` (**development overlay only**) |

Frontend origin default: `http://localhost:9398` (`FRONTEND_ORIGIN`, comma-separated). CORS allows listed origins with credentials.

Dev (non-Compose): Vite listens on **8080** and proxies `/api`, `/health`, and `/mcp` to `localhost:8000`. Compose `web` uses **9398** by default so Vite and Compose can run side by side.

---

## Process roles

### API

- Serves REST and OpenAPI.
- Authenticates cookie sessions.
- Writes documents/metadata and **enqueues** jobs; does not run OCR/indexing in-request except Ask/search embedding of the **query** when semantic/hybrid search is requested.
- Bootstrap on startup: storage directories, first admin, system folders, `ai_settings` row.

### Worker

Loop (sleep `JOB_POLL_INTERVAL_SECONDS`, default 2s):

1. Requeue stale `RUNNING` jobs (startup: all running; loop: heartbeat older than `JOB_STALE_RUNNING_SECONDS`).
2. Claim up to `JOB_CONCURRENCY` jobs.
3. Poll `/consume` for stable files.
4. Periodically purge expired trash.
5. Fire-and-forget AI provider probes (must not block OCR).

### Web

Serves `frontend/dist`. Proxies API. SPA fallback `try_files` → `index.html`. `client_max_body_size 110m` (aligned with default 100 MB upload plus overhead).

---

## Source-built vs distributable

Public Compose uses `image:` tags on GHCR (`ghcr.io/brocxftw/lesspaper-ngl-backend` and `lesspaper-ngl-web`). Contributors overlay `compose.dev.yaml` to `build:` from this tree.

- Frontend is compiled **inside** the `web` image; runtime `web` does not mount SPA source.
- Backend image copies `backend/src` at **build** time. Public Compose does **not** bind-mount source. `docker-compose.debug.yml` **does** mount `./backend/src` for live API/worker code.
- Bind mounts for **data** (`./data/documents` etc.) are runtime, not source.

Operators: [interactive installer](../deployment/installer.md), or download Release Compose + `env.example` → `docker compose up -d`. Contributors: `docker compose -f docker-compose.yml -f compose.dev.yaml up --build -d`.

---

## Identity and version

`GET /health` `version` comes from `LESSPAPER_NGL_VERSION` (leading `v` stripped), else `git describe`, else `0.1.0`. Published images set `LESSPAPER_NGL_VERSION`, `LESSPAPER_NGL_BUILD_REVISION`, and `LESSPAPER_NGL_BUILD_DATE` at build time. Compose can pin the **image tag** with `LESSPAPER_NGL_VERSION` independently of that metadata.

---

## Concurrency and isolation

- One worker process per `worker` container; in-process asyncio semaphore = `JOB_CONCURRENCY` (default 1). OCR holds an exclusive gate and runs Paddle in a short-lived subprocess by default.
- Inbox **preflight** jobs are gated so only one still-preparing Inbox document is claimed at a time (oldest first).
- Trashed-document jobs are skipped/cancelled so deletes do not starve the queue.
- OCR uses a dedicated thread executor (Paddle constraint).

---

## Failure domains

| Failure | Effect |
|---------|--------|
| `db` down | API/worker cannot start or serve |
| `/documents` unwritable | Uploads rejected; metadata remains |
| `/consume` unwritable | Consume ingest stops; `/health/storage` degraded if documents still OK |
| AI provider down | Jobs that need AI fail/retry/soft-fail; keyword DMS continues; `/health` still `ok` |
| `web` down | UI unavailable; API still on :8000 |
