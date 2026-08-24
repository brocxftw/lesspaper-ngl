# Upgrades and rollback

Operators pull published GHCR images. `git pull` and `docker compose build` are for contributors, not production installs.

## Update with the host CLI (primary)

On the Docker host / CT:

```bash
lesspaper-ngl update                 # newest beta prerelease (default)
lesspaper-ngl update beta            # same
lesspaper-ngl update latest          # newest stable
lesspaper-ngl update v0.1.24-beta.5  # exact pin
```

`lesspaper-ngl update` downloads a fresh `install-lesspaper-ngl.sh` (falls back to `install-folium.sh`) for that channel/tag and runs the noninteractive update path. Secrets, bind, ports, and storage paths are preserved.

If `/usr/local/bin/lesspaper-ngl` still stubs `update`, refresh the CLI once with the installer below, then use `lesspaper-ngl update` afterward.

## Update with the installer

Re-run `install-lesspaper-ngl.sh`. When it detects an existing install, choose **Update**. That keeps `.env` secrets and document data, pulls the pinned release images, and restarts the stack.

```bash
curl -fsSL -o install-lesspaper-ngl.sh \
  https://github.com/brocxftw/lesspaper-ngl/releases/latest/download/install-lesspaper-ngl.sh
less install-lesspaper-ngl.sh
bash install-lesspaper-ngl.sh
```

Non-interactive updates (secrets and bind settings are preserved):

```bash
# Newest stable
bash install-lesspaper-ngl.sh --noninteractive --update --version latest --json

# Newest prerelease
bash install-lesspaper-ngl.sh --noninteractive --update --version beta --json

# Exact pin (stable or beta)
bash install-lesspaper-ngl.sh --noninteractive --update --version v0.1.24-beta.5 --json
```

`--version` overrides the currently installed version recorded in `install-state.json` / `.env`.

To run the installer script from a specific prerelease asset (instead of `releases/latest`), download that tag’s `install-lesspaper-ngl.sh` from [Releases](https://github.com/brocxftw/lesspaper-ngl/releases).

## Update to a newer release (manual Compose)

Edit `.env` (canonical `LESSPAPER_NGL_*`; legacy `FOLIUM_*` still accepted):

```text
LESSPAPER_NGL_VERSION=0.2.0
```

For a prerelease pin, use the tag without the leading `v`:

```text
LESSPAPER_NGL_VERSION=0.1.24-beta.5
```

Then:

```bash
docker compose pull
docker compose up -d
```

The API container runs `alembic upgrade head` before serving traffic. The worker waits until the API is healthy, then processes jobs against the migrated schema.

`docker compose pull` + `up -d` does **not** remove the Postgres volume or host document binds.

## Update using `latest` or `beta`

If `LESSPAPER_NGL_VERSION=latest`, `docker compose pull` fetches the most recent **stable** image tag (`vX.Y.Z` with no prerelease suffix). Prerelease tags (`vX.Y.Z-beta.N`) publish a moving `beta` tag instead and do not replace `latest`.

The installer and `lesspaper-ngl update` accept aliases `latest` and `beta`, resolve them to a pinned release, and store that pin in `.env` / `install-state.json`. Prefer pinning `LESSPAPER_NGL_VERSION` (for example `0.1.24-beta.5`) so the Compose file, `.env`, and images stay aligned.

## What is not an upgrade path

- `git pull` and `docker compose build` are for **contributors**, not operators.
- Do not use `docker compose down -v` during an upgrade.

## Rollback

You may point `LESSPAPER_NGL_VERSION` at an older image tag and `docker compose pull && docker compose up -d`.

**Application image rollback does not roll back the database.** Alembic migrations are forward-only in this project. If version B migrated the schema, returning to image A can fail or corrupt data if A cannot read the new schema.

Safe rollback is limited to:

- configuration (`.env`) that version A understands
- images **before** a schema-changing release, or
- restoring a **backup taken before** the upgrade ([backup](backup.md))

Do not assume lesspaper-ngl supports mixed application/schema versions.
