# Install lesspaper-ngl (images)

**Primary path:** the [interactive installer](installer.md). This page is the manual Compose alternative.

Requirements: Docker and Docker Compose on **linux/amd64**. ARM is unsupported.

## GHCR packages must be public

Anonymous `docker compose up` needs public packages:

- `ghcr.io/brocxftw/lesspaper-ngl-backend`
- `ghcr.io/brocxftw/lesspaper-ngl-web`

**One-time maintainer step after the first successful publish:** GitHub → Packages → each package → Package settings → Change package visibility → **Public**. Link the package to the `brocxftw/lesspaper-ngl` repository if GitHub has not already done so from OCI `org.opencontainers.image.source`.

End users must **not** run `docker login ghcr.io`.

## Install

Stable (newest non-prerelease):

```bash
mkdir lesspaper-ngl
cd lesspaper-ngl

curl -fsSL -o docker-compose.yml \
  https://github.com/brocxftw/lesspaper-ngl/releases/latest/download/docker-compose.yml
curl -fsSL -o env.example \
  https://github.com/brocxftw/lesspaper-ngl/releases/latest/download/env.example

cp env.example .env
```

### Pre-release / beta

`releases/latest` never points at a prerelease. Download assets from a specific prerelease tag instead:

```bash
TAG=v0.1.24-beta.5   # example — pick a tag from GitHub Releases

mkdir lesspaper-ngl
cd lesspaper-ngl

curl -fsSL -o docker-compose.yml \
  "https://github.com/brocxftw/lesspaper-ngl/releases/download/${TAG}/docker-compose.yml"
curl -fsSL -o env.example \
  "https://github.com/brocxftw/lesspaper-ngl/releases/download/${TAG}/env.example"

cp env.example .env
```

Ensure `.env` sets `LESSPAPER_NGL_VERSION` (legacy `FOLIUM_VERSION` still accepted) to the tag without the leading `v` (for example `0.1.24-beta.5`). Prefer that pin over the moving GHCR `beta` tag.

For the installer-based beta path, see [installer.md](installer.md#pre-release--beta).

Edit `.env`:

1. `LESSPAPER_NGL_SECRET_KEY` and `LESSPAPER_NGL_ENCRYPTION_KEY` — `openssl rand -hex 32` for each
2. `POSTGRES_PASSWORD` — required; use hex (`openssl rand -hex 24`). Do not use `@ : / # ?` in the password
3. `LESSPAPER_NGL_ADMIN_PASSWORD` — first-boot admin only
4. `FRONTEND_ORIGIN` — comma-separated browser URLs (default `http://localhost:9398`)
5. Host bind paths if you do not want `./data/...`

```bash
mkdir -p data/documents data/consume data/export data/backups data/paddleocr
# containers run as UID 1000
sudo chown -R 1000:1000 data/documents data/consume data/export data/backups data/paddleocr

docker compose up -d
```

UI: http://localhost:9398  
Health (via nginx): http://localhost:9398/health  
OpenAPI: http://localhost:9398/docs (or http://localhost:9099/docs if you publish the API port)

MCP: http://localhost:9398/mcp (Bearer API token; proxied through `web`)

Bootstrap admin is created **only** when the users table is empty.

Open registration defaults to **off**. Add further users with admin invites.

## Persistence names

By design these keep their historical Folium identifiers: Postgres role/database `folium`, volume `folium_pgdata`, cookies `folium_session` / `folium_csrf`, backup extension `.folium`.

## What Docker pulls

| Service | Image |
|---------|--------|
| `api`, `worker` | `ghcr.io/brocxftw/lesspaper-ngl-backend:<version>` |
| `web` | `ghcr.io/brocxftw/lesspaper-ngl-web:<version>` |
| `db` | `pgvector/pgvector:pg17` (upstream) |

Release Compose files default `LESSPAPER_NGL_VERSION` to that release (for example `0.1.16`), so you do not accidentally pull a newer `latest` than the files you downloaded.

## First OCR run

PaddleOCR models download into the `LESSPAPER_NGL_PADDLE_CACHE_HOST` bind on first OCR. Keep that directory on local disk.

## Extra host GID (optional)

Public Compose does not add extra groups. If a bind mount is `0770` for a host group, create a gitignored `docker-compose.override.yml`:

```yaml
services:
  api:
    group_add:
      - "10000"
  worker:
    group_add:
      - "10000"
```

## Next

- [Upgrades](upgrades.md)
- [Backup](backup.md)
- [Environment variables](environment-variables.md)
- Source-build (contributors): [local development](../development/local-development.md)
