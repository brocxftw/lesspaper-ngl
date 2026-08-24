# Docker

## Service table

| Service | Purpose | Image | Command | Depends on |
|---------|---------|-------|---------|------------|
| `db` | PostgreSQL 17 + pgvector | Pulled `pgvector/pgvector:pg17` | image default | — |
| `api` | FastAPI | Pulled `ghcr.io/brocxftw/lesspaper-ngl-backend` | `alembic upgrade head` then uvicorn | `db` healthy |
| `worker` | Jobs + consume + purge | **Same** backend image | `lesspaper-ngl-worker` (legacy `folium-worker` accepted) | `db` + `api` healthy |
| `web` | SPA + reverse proxy | Pulled `ghcr.io/brocxftw/lesspaper-ngl-web` | nginx | `api` healthy |

Restart: `unless-stopped` on all four. `security_opt: no-new-privileges:true` on app containers. `api`/`worker` `user: "1000:1000"`. Public Compose does **not** set `group_add`.

## Images

Persistence note: Compose volume key `folium_pgdata` and default Postgres role/db `folium` are intentional.


**Backend:** `python:3.13-slim-bookworm`, pinned `uv`, PaddlePaddle CPU + `.[ocr]`, Alembic, entrypoint `docker/backend-entrypoint.sh`. Exposes 8000. Same image for API and worker.

**Frontend:** multi-stage `node:20` `npm ci && npm run build` → `nginx:1.27-alpine` + `docker/nginx.conf`.

Build context for contributors is the **repository root**. Published tags: `X.Y.Z` and `X.Y` plus `latest` for **stable** tags; prerelease tags (`X.Y.Z-beta.N`) also publish `beta` and must not move `latest` or `X.Y`. Every image also gets `sha-<shortsha>`. Platform: **linux/amd64**. ARM is untested.

OCI labels include source URL `https://github.com/brocxftw/lesspaper-ngl` and licence `AGPL-3.0-only`. Build-args set `LESSPAPER_NGL_VERSION`, `LESSPAPER_NGL_BUILD_REVISION`, `LESSPAPER_NGL_BUILD_DATE`.

## Compose files

| File | Role |
|------|------|
| `docker-compose.yml` | Public: `image:` only (GitHub Release asset) |
| `compose.dev.yaml` | Overlay: `build:` + Postgres `5433` |
| `docker-compose.debug.yml` | Optional live Python mounts |

Contributor command:

```bash
docker compose -f docker-compose.yml -f compose.dev.yaml up --build -d
```

`make build` / `make up` use that overlay.

## Ports

Public: `9398:80` (web), `9099:8000` (api). Postgres is **not** published. The development overlay maps `5433:5432`.

## Migrations

Only the **api** entrypoint runs Alembic. Failures abort startup (`set -e`). Worker waits until api is healthy so it never processes against an unmigrated schema.

## Publishing

`.github/workflows/publish-images.yml` runs on `v*` tags: tests, amd64 build, compose smoke (`GET /health`), push to GHCR, upload Release assets (`docker-compose.yml`, `env.example`, `default.env.example`, standalone `install-lesspaper-ngl.sh` plus `install-folium.sh` shim, `checksums.txt`). Tags with a prerelease suffix (`v0.1.24-beta.1`) create a GitHub **prerelease**, publish the `beta` image tag, and do not update `latest`. Packages must be made **public** once (see [install](install.md)).
