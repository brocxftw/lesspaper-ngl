# lesspaper-ngl documentation

Folium has been renamed to lesspaper-ngl.

Engineering docs derived from the **active codebase**. The root [README](../README.md) is the public front door; it must not outrun this tree.

Product vocabulary: [`ubiquitous-language.md`](../ubiquitous-language.md). Licence: [GNU AGPL v3.0](../LICENSE).

```text
CODE  →  docs/  →  README.md
```

## Architecture

| Document | Description |
|----------|-------------|
| [Overview](architecture/overview.md) | What lesspaper-ngl is, boundaries, main flows (~10 min) |
| [Runtime](architecture/runtime-architecture.md) | Compose processes, ports, images vs source-build |
| [Data model](architecture/data-model.md) | Entities, ownership, derived vs canonical |
| [Document lifecycle](architecture/document-lifecycle.md) | Upload → Inbox → Process → index/embed → trash |
| [Storage](architecture/storage.md) | Content-addressed files, mounts, NFS |
| [Jobs and workers](architecture/jobs-and-workers.md) | Queue, job types, indexing vs embedding |
| [Security and privacy](architecture/security-and-privacy.md) | Sessions, CSRF, PrivacyGate |

## Backend

| Document | Description |
|----------|-------------|
| [Overview](backend/overview.md) | Layers and package map |
| [API](backend/api.md) | Capability groups (OpenAPI remains authoritative) |
| [Services](backend/services.md) | Domain service boundaries |
| [Database](backend/database.md) | Postgres, pgvector, FTS, migrations |
| [Ingestion](backend/ingestion.md) | AI and non-AI ingest paths |
| [Search and retrieval](backend/search-and-retrieval.md) | Browse vs evidence search; modes |
| [AI and RAG](backend/ai-and-rag.md) | Suggestions, embeddings, Ask |
| [Configuration](backend/configuration.md) | Env vs database settings |

## Frontend

| Document | Description |
|----------|-------------|
| [Overview](frontend/overview.md) | React/Vite app structure |
| [App shell](frontend/app-shell.md) | Navigation (actual routes only) |
| [Workspaces](frontend/workspaces.md) | Inbox, Documents, Search, Ask, Jobs, Trash, Settings |
| [Domain components](frontend/domain-components.md) | Viewer, inspector, drawers, Inbox |
| [State and API](frontend/state-and-api.md) | React Query, CSRF, preferences |
| [Design system](frontend/design-system.md) | Tailwind tokens and primitives |

## Deployment

| Document | Description |
|----------|-------------|
| [Overview](deployment/overview.md) | Image-based Compose model |
| [Installer](deployment/installer.md) | Whiptail TUI; GHCR pull or source build |
| [Install](deployment/install.md) | Manual GHCR pull; no git clone |
| [Upgrades](deployment/upgrades.md) | `compose pull` / rollback limits |
| [Backup](deployment/backup.md) | `.folium` bundles, `/backups` mount, first-run restore |
| [Docker](deployment/docker.md) | Services, images, entrypoints |
| [Storage mounts](deployment/storage-mounts.md) | Binds and volumes |
| [Environment variables](deployment/environment-variables.md) | Verified env reference |
| [Healthchecks](deployment/healthchecks.md) | Container vs app vs AI |
| [Production readiness](deployment/production-readiness.md) | Public-release status + licences |

## Development

| Document | Description |
|----------|-------------|
| [Local development](development/local-development.md) | Host uvicorn/Vite + db |
| [Repository structure](development/repository-structure.md) | Tree |
| [Testing](development/testing.md) | pytest, vitest, CI gaps |
| [Contributing](development/contributing.md) | What the repo actually encodes |

## ADRs

[Architecture Decision Records](adr/README.md) — optional AI, Inbox/Process, CAS folders, Postgres queue, host NFS.

## Audit / reference

| Document | Description |
|----------|-------------|
| [Repository inventory](audit/repository-inventory.md) | Evidence-backed codebase inventory |
| [UI/UX audit](ui-ux/LESSPAPER_NGL_UI_UX_AUDIT.md) | 2026-08-10 UI reverse-engineering; **stale** on Ask conversations |
