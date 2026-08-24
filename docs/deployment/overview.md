# Deployment overview

Folium has been renamed to lesspaper-ngl.

## Supported model

Operators typically run the [interactive installer](installer.md). The equivalent manual path is GitHub Release Compose + `env.example` — no git clone and no lesspaper-ngl image build.

```text
download docker-compose.yml
download env.example
configure .env
docker compose up -d
```

Step-by-step: [Installer](installer.md) (including [pre-release / beta](installer.md#pre-release--beta)) or [manual install](install.md).

Postgres is pulled from Docker Hub (`pgvector/pgvector:pg17`). lesspaper-ngl `api`/`worker`/`web` are pulled from GHCR.

## What you get

| URL | Service |
|-----|---------|
| http://localhost:9398 | UI |
| http://localhost:9398/health | API liveness + version (nginx proxy) |
| http://localhost:8000/docs | OpenAPI (published by public Compose; installer leaves 8000 unpublished unless opted in) |

First boot creates the bootstrap admin from `LESSPAPER_NGL_ADMIN_USERNAME` / `LESSPAPER_NGL_ADMIN_PASSWORD` if no users exist.

## Contributors

Clone the repository and source-build with [compose.dev.yaml](../../compose.dev.yaml):

```bash
docker compose -f docker-compose.yml -f compose.dev.yaml up --build -d
```

See [local development](../development/local-development.md).

## Further reading

- [Installer](installer.md)
- [Install](install.md)
- [Upgrades](upgrades.md)
- [Backup](backup.md)
- [Docker](docker.md)
- [Storage mounts](storage-mounts.md)
- [Environment variables](environment-variables.md)
- [Healthchecks](healthchecks.md)
- [Production readiness](production-readiness.md)
