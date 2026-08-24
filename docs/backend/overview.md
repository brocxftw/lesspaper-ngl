# Backend overview

The backend is the Python package `lesspaper_ngl` (FastAPI, SQLAlchemy 2 asyncio, Alembic, Pydantic Settings). Python **≥ 3.13**. OCR extra (`paddleocr`) is installed in Docker, not in default CI.

---

## Responsibilities

- Authenticate users and enforce owner isolation
- Persist library metadata and job state
- Ingest bytes to content-addressed storage
- Expose search and Ask
- Configure AI policy/providers (optional)
- Serve health, about, logs, system diagnostics

It does **not** mount NFS, run a second queue broker, or embed a frontend (the `web` image does).

---

## Layers

```text
FastAPI routes (folium.api.*)
        ↓
Domain services (folium.services.*)
        ↓
SQLAlchemy models / PostgreSQL

API / services enqueue Job rows
        ↓
Worker (folium.workers.*)
        ↓
OCR / chunking / embeddings / AI adapters
```

**Confirmed:** substantial domain logic lives in services and the worker, not only in route handlers. Search and RAG have dedicated packages (`folium.search`, `folium.ai`).

---

## Package map (architectural, not every file)

| Area | Location |
|------|----------|
| App factory, CORS, logging middleware | `folium.main` |
| Settings | `lesspaper_ngl.core.config` |
| Auth | `folium.auth` |
| HTTP API | `folium.api` |
| ORM | `folium.models` |
| Storage | `folium.storage.service` |
| OCR / extract | `folium.ocr` |
| Jobs API helpers | `folium.services.jobs` |
| Worker loop | `folium.workers.main` |
| Job handlers | `folium.workers.processor` |
| CLI | `folium.cli` (`reset-admin-password`) |

Entrypoints from `pyproject.toml`: `lesspaper_ngl`, `lesspaper-ngl-api`, `lesspaper-ngl-worker`.

---

## Error handling

`folium.api.errors` registers handlers for domain exceptions (`AuthError`, `ForbiddenError`, `ValidationError`, `PrivacyViolationError`, `StorageUnavailableError`, `DuplicateDocumentError`, …). Request IDs flow via `X-Request-ID`.

---

## See also

- [API](api.md)
- [Services](services.md)
- [Database](database.md)
- [Ingestion](ingestion.md)
- [Search and retrieval](search-and-retrieval.md)
- [AI and RAG](ai-and-rag.md)
- [Configuration](configuration.md)
