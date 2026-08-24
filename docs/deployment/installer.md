# Interactive installer

Primary install path for operators. A [manual Compose install](install.md) remains supported.

## Quick start

Review the installer script, then run it. It is a single file (no tarball):

```bash
curl -fsSL -o install-lesspaper-ngl.sh \
  https://github.com/brocxftw/lesspaper-ngl/releases/download/beta/install-lesspaper-ngl.sh
less install-lesspaper-ngl.sh
bash install-lesspaper-ngl.sh
```

That `beta` URL is a moving pointer to the newest prerelease. Do not treat `| bash` as the only option. Pin an exact tag from [Releases](https://github.com/brocxftw/lesspaper-ngl/releases) if you need a specific `vX.Y.Z-beta.N`.

Releases also publish `install-folium.sh` as an identical transition shim (same contents as `install-lesspaper-ngl.sh`). GitHub’s `/releases/latest/download/` is unpublished until a stable `vX.Y.Z` exists.

### Pre-release / beta

Prereleases use tags like `vX.Y.Z-beta.N`. They are published as GitHub **prereleases**. The moving Release/tag `beta` always holds the current prerelease installer and Compose assets (and GHCR publishes a moving `beta` image tag).

**Interactive:** download the moving beta installer, then pick a **Beta**-labelled tag in the version picker if you want a pin other than the newest prerelease:

```bash
curl -fsSL -o install-lesspaper-ngl.sh \
  https://github.com/brocxftw/lesspaper-ngl/releases/download/beta/install-lesspaper-ngl.sh
less install-lesspaper-ngl.sh
bash install-lesspaper-ngl.sh
```

**Non-interactive** (fresh install or update):

```bash
# Newest prerelease
bash install-lesspaper-ngl.sh --noninteractive --version beta --json

# Exact prerelease pin
bash install-lesspaper-ngl.sh --noninteractive --version v0.1.24-beta.5 --json

# Update existing install to newest beta (preserves secrets / bind)
bash install-lesspaper-ngl.sh --noninteractive --update --version beta --json
```

CLI `--version` and process-environment `LESSPAPER_NGL_VERSION` / `LESSPAPER_NGL_VERSION_TAG` take precedence over the version already stored in `install-state.json` or `.env`. The installer still resolves aliases to a pinned `vX.Y.Z-beta.N` before writing state.

The script is a packed copy of `installer/install.sh` plus its libraries. It starts a **whiptail** TUI and then downloads that release’s `docker-compose.yml`.

From a git checkout (contributors; modular sources):

```bash
bash installer/install.sh
# rebuild the curl-able file:
bash installer/pack.sh /tmp/install-lesspaper-ngl.sh
# also writes install-folium.sh alongside when the outfile basename is install-lesspaper-ngl.sh
```

## What the installer does

1. Checks linux/amd64, Docker, disk, and memory. ARM is a hard failure.
2. Offers to install Docker Engine via `get.docker.com` only after confirmation.
3. Detects an existing install and offers **Update** (pull a pinned release image), Reconfigure, Repair, or Exit. It never silently rewrites `.env` secrets.
4. Chooses **pre-built GHCR images** (default) or **build from source** (clones the selected tag into `INSTALL_DIR/src`).
5. Pins a real `vX.Y.Z` or `vX.Y.Z-beta.N` release. It never stores `latest` or the moving `beta` image tag as the installed version.
6. Writes `/opt/lesspaper-ngl` by default for fresh installs (you may choose another directory; `/root` and `/tmp` are allowed at your own risk with a confirmation). Existing installs under `/opt/folium` are still discovered and are not force-moved. Release `docker-compose.yml`, a small overlay (bind/port/`group_add` only), and `.env` (`chmod 600`). Backup files go to `$INSTALL_DIR/data/backups` (not the installer config snapshot folder).
7. Publishes **only the UI port** (default **9398**). The API host port (default **9099**) is unpublished unless you opt in. Nginx in `web` already proxies `/api`, `/health`, and `/mcp`.
8. Waits for `GET /health`, `/health/database`, `/health/storage`, and `/health/worker`. AI health is ignored.
9. Installs `/usr/local/bin/lesspaper-ngl` (`status`, `start`, `stop`, `restart`, `logs`, `doctor`, `update`) and a `/usr/local/bin/folium` shim. `uninstall` remains a stub in v1.

Secrets are generated with `openssl rand`. The bootstrap admin password is shown **once** on the success screen and is not written to the installer log. The welcome screen shows the exact log file path for that run (for example `/tmp/folium-install-20260817-123456.log`).

The TUI keeps a blue screen behind a **grey** dialog card. Cancel is labeled **Back**, and menus also include an explicit **Back** item where useful. Ctrl+C cancels immediately (restores the terminal; existing data is not deleted). Install progress (pull/build/start/health) is shown with a gauge; Compose output goes to the log file.

There is no timezone prompt. lesspaper-ngl timestamps are UTC.

## Layout

```text
/opt/lesspaper-ngl/
  docker-compose.yml
  docker-compose.override.yml
  .env                    # mode 600
  install-state.json      # no secrets
  backups/                # installer config snapshots only — not lesspaper-ngl bundles
  data/backups/           # default host bind for /backups (.folium bundles)
  data/paddleocr/         # always local, even if documents are on NAS
  installer/              # packed `lesspaper-ngl` CLI (or modular copy from a git install)
```

Paddle OCR cache is always under the install directory. Document/consume/export binds may be existing host paths, including NFS/CIFS mounts **already present**. The installer does not edit `/etc/fstab` and does not install NAS client packages.

`FRONTEND_ORIGIN` lists every browser URL you will use (comma-separated), for example `https://docs.example.com,http://192.168.1.10:9398`. If you use a reverse proxy on HTTPS but keep an HTTP LAN origin in the list, set `LESSPAPER_NGL_SECURE_COOKIES=true` so session cookies use the `Secure` flag. The installer does not install Caddy or nginx on the host.

**MCP:** Streamable HTTP at `{origin}/mcp` through the UI port (recommended). Requires a Bearer API token from Settings → Profile. Optional: publish the API port and use `http://host:9099/mcp` directly.

Non-interactive installs under `/root` or `/tmp` require `LESSPAPER_NGL_ACCEPT_RISKY_PATH=1`.

## Management CLI

```bash
lesspaper-ngl status
lesspaper-ngl start
lesspaper-ngl stop
lesspaper-ngl restart
lesspaper-ngl logs
lesspaper-ngl doctor
lesspaper-ngl update                 # newest beta (default); also: latest | vX.Y.Z[-beta.N]
```

`lesspaper-ngl update` downloads a fresh release installer and runs `--noninteractive --update`. Override the install directory with `LESSPAPER_NGL_INSTALL_DIR`. The CLI also reads `/etc/lesspaper-ngl/install-dir` (and legacy `/etc/folium/install-dir`).

Hosts still on an older CLI stub need one installer re-run before `update` is available.

## Non-interactive (automation / CI / agents)

`--noninteractive` is the automation entry point. When an existing install is
discovered (via `/etc/lesspaper-ngl/install-dir`, legacy `/etc/folium/install-dir`, `/opt/folium`, `install-state.json`, or
`LESSPAPER_NGL_INSTALL_DIR` with `.env` + Compose), the installer runs the **update**
path: secrets, bind, ports, and storage paths are preserved from `.env`. A
fresh install only runs when no existing install is found.

```bash
# Fresh install of a pinned release
LESSPAPER_NGL_UI=none LESSPAPER_NGL_NONINTERACTIVE=1 \
  LESSPAPER_NGL_VERSION=0.1.16 LESSPAPER_NGL_VERSION_TAG=v0.1.16 \
  LESSPAPER_NGL_INSTALL_DIR=/tmp/folium-installer-smoke \
  LESSPAPER_NGL_BIND=127.0.0.1 LESSPAPER_NGL_HTTP_PORT=18080 \
  LESSPAPER_NGL_COMPOSE_PROJECT=folium-installer-smoke \
  LESSPAPER_NGL_SKIP_CLI=1 \
  LESSPAPER_NGL_ACCEPT_RISKY_PATH=1 \
  LESSPAPER_NGL_RELEASE_COMPOSE_FILE=/path/to/docker-compose.yml \
  bash installer/install.sh --noninteractive

# Update existing install to newest beta (secrets kept automatically)
bash install-lesspaper-ngl.sh --noninteractive --update --version beta --json

# Update to a pinned prerelease
bash install-lesspaper-ngl.sh --noninteractive --update --version v0.1.24-beta.5 --preserve-secrets --json
```

CLI flags (aliases for the matching `LESSPAPER_NGL_*` env vars; legacy `FOLIUM_*` still accepted):

| Flag | Effect |
|------|--------|
| `--noninteractive` | No TUI (`LESSPAPER_NGL_UI=none`) |
| `--update` | Force update path (implies `--noninteractive`) |
| `--version <tag>` | Pin `vX.Y.Z` / `vX.Y.Z-beta.N`, or aliases `latest` / `beta` |
| `--preserve-secrets` | Keep existing `.env` secrets (`LESSPAPER_NGL_KEEP_SECRETS=1`) |
| `--json` | Print one JSON summary line on completion |

Version aliases resolve to a **pinned** tag before writing `.env` / state:
`beta` → newest prerelease (`vX.Y.Z-beta.N`); `latest` → GitHub `releases/latest`
(stable; unpublished until a non-prerelease exists). Moving image tags are never stored as the installed version.

Exit codes:

| Code | Meaning |
|------|---------|
| `0` | Success and health checks passed |
| `1` | Install/update failed |
| `2` | Bad arguments / config |
| `3` | Completed but health checks failed |
| `130` | Interrupted (Ctrl+C) |

`--json` emits a single line such as:

```json
{"version":"0.1.24-beta.2","version_tag":"v0.1.24-beta.2","healthy":true,"install_dir":"/opt/lesspaper-ngl","frontend_origin":"https://docs.example.com","mode":"update"}
```

Non-interactive installs under `/root` or `/tmp` require `LESSPAPER_NGL_ACCEPT_RISKY_PATH=1`.

## Tests

```bash
bash installer/tests/run.sh
# optional live smoke (throwaway project, non-8080 port):
bash installer/tests/smoke.sh
```

CI runs ShellCheck and `installer/tests/run.sh`.

### Manual matrix (not fully automated)

| Case | Coverage |
|------|----------|
| Happy path, pre-built images, localhost:18080 | `smoke.sh` / operator TUI |
| Existing install: Update / Reconfigure / Repair / Exit | TUI on a host with `/opt/lesspaper-ngl` or legacy `/opt/folium` |
| Source build (`git clone` + `compose.source.yaml`) | Manual |
| LAN bind `0.0.0.0` + detected IPv4 origin | Manual |
| Comma-separated `FRONTEND_ORIGIN` (proxy + LAN) | Manual |
| Install under `/root` or `/tmp` (risky path confirm) | Manual |
| Existing NFS/CIFS binds + extra GID | Manual (no fstab edits) |
| Occupied HTTP port | Installer asks for another port (does not exit) |
| Non-amd64 | Hard-fail in `system_check` (needs an ARM host) |
| Docker missing → get.docker.com | Manual / VM |
| Ctrl+C during TUI | Restores tty; does not delete data |

A development host that already runs lesspaper-ngl on 9398/9099 must use another Compose project name and HTTP port for installer smokes.

## Release assets

Each `v*` GitHub Release includes:

- `install-lesspaper-ngl.sh` (standalone installer; preferred)
- `install-folium.sh` (identical transition shim)
- `docker-compose.yml`
- `env.example` (canonical env template)
- `default.env.example` (compatibility alias; GitHub rejects a leading-dot `.env.example` asset name)
- `checksums.txt`

Prerelease publishes also refresh a moving GitHub Release/tag named `beta` with those same assets, so `/releases/download/beta/<asset>` always tracks the newest prerelease. The installer version picker lists **prereleases** (`vX.Y.Z-beta.N`, labelled Beta) and omits the moving channel tags `beta` / `latest`. Until a stable `vX.Y.Z` exists, curl the moving installer at `/releases/download/beta/install-lesspaper-ngl.sh` (or pass `--version beta`). That resolves to a pinned `vX.Y.Z-beta.N` before writing state.
