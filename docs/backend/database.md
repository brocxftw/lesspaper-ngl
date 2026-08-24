# Database

## Role

PostgreSQL 17 with the **pgvector** extension is the system of record for:

- Users, sessions, library metadata
- Page text and **full-text search** (`tsvector` / `tsquery`, config `english`)
- Chunk text and **embeddings**
- Job queue
- AI settings/providers/usage
- Application logs and library counters

There is no separate search engine or queue database.

---

## pgvector

`document_chunks.embedding` is `Vector(3072)`. Smaller model vectors are **padded**. Queries filter by `embedding_provider`, `embedding_model`, and `embedding_dimension` (active embedding space on `ai_settings`).

---

## Migrations

Alembic, `backend/alembic/versions/`:

| Rev | Topic |
|-----|--------|
| 001 | Initial schema |
| 002 | Trash retention |
| 003 | Multi-user |
| 004 | Avatar / password reset |
| 005 | Settings workspace |
| 006 | Job `available_at` |
| 007 | Embedding pipeline fields |
| 008 | Library activity counters |
| 009 | OCR page progress |
| 010 | Semantic min score |
| 011 | Ask conversations |

API container runs `alembic upgrade head` on start. Worker does not.

---

## Transactions

Typical API request = one `AsyncSession`. Worker: new `session_scope` per claim/complete and for OCR progress commits. Process uses nested transactions per document in a batch so one failure does not roll back the whole batch.

---

## Persistence

Compose volume `folium_pgdata` → `/var/lib/postgresql/data`. Host port 5433 for local tools. Default credentials in Compose are **hard-coded** (`lesspaper_ngl`/`lesspaper_ngl`); `DATABASE_URL` in `.env` is overridden by Compose `environment:` for `api`/`worker`.
