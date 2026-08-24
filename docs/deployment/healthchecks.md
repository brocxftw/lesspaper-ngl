# Healthchecks

## Container checks (Compose)

| Service | Test | Notes |
|---------|------|-------|
| `db` | `pg_isready` with container `POSTGRES_USER` / `POSTGRES_DB` | Required for api/worker start |
| `api` | `curl -sf http://127.0.0.1:8000/health` | Does **not** check DB, storage, worker, or AI |
| `web` | `wget -qO- http://127.0.0.1/` | Static nginx |
| `worker` | `python -m folium.workers.healthcheck` | Sync DB read of `worker_heartbeat`; stale after 90s |

The worker writes `worker_heartbeat` on a background task (~10s) so long OCR jobs do not starve liveness.

## Application endpoints

| Path | Auth | Checks |
|------|------|--------|
| `GET /health` | No | Process up; `version` |
| `GET /health/database` | No | `SELECT 1` |
| `GET /health/worker` | No | Heartbeat freshness; `healthy` / `unavailable` |
| `GET /health/storage` | No | Writability of documents/consume/export |
| `GET /api/ai/health` | Yes | Assigned provider probes |

**Confirmed:** an unavailable AI provider does **not** fail `GET /health` or the api Compose healthcheck. lesspaper-ngl remains a document manager when AI is down. Worker unavailability does **not** fail `GET /health`.

Storage `status`: `ok` \| `degraded` (documents OK, consume/export not) \| `unavailable` (documents not writable).
