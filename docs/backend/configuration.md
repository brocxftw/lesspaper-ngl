# Configuration

## Precedence

**Confirmed** (`pydantic-settings`):

1. Process environment variables (always win)
2. Env files `.env` then `../.env` relative to CWD
3. Field defaults in `lesspaper_ngl.core.config.Settings`

Compose injects `DATABASE_URL*` and path env on `api`/`worker`, overriding `.env` database host (`db` vs `localhost`).

AI **policy defaults** from env apply only when the `ai_settings` row is **first created**. Later changes are database-backed (Settings UI). Env `AI_PRIVACY_MODE` etc. do not continuously override the singleton.

---

## Application settings (`Settings`)

See the environment variable table in [deployment/environment-variables.md](../deployment/environment-variables.md). Every `alias=` on `Settings` is listed there.

Additional runtime reads:

| Variable | Reader | Notes |
|----------|--------|-------|
| `LESSPAPER_NGL_VERSION` | `lesspaper_ngl.core.version` | Not a `Settings` field |
| `PADDLE_PDX_*` | Paddle / Dockerfile | OCR cache; not in Settings |

---

## Database-backed

- `ai_settings`, `ai_providers`, `ai_model_assignments`
- `app_settings` (worker heartbeat)
- Per-user quotas on `users`

---

## Storage paths

`DOCUMENTS_PATH`, `CONSUME_PATH`, `EXPORT_PATH` must match Compose volume **targets**. Host sources are Compose-only (`LESSPAPER_NGL_DOCUMENTS_HOST`, …).

---

## Frontend

Vite/nginx do not load lesspaper-ngl `Settings`. CSRF cookie name is hard-coded in the SPA. `FRONTEND_ORIGIN` is a comma-separated list of browser URLs (CORS + MCP). Set `LESSPAPER_NGL_SECURE_COOKIES=true` when users reach the UI over HTTPS via a reverse proxy but an HTTP LAN URL remains in the list.
