# lesspaper-ngl

> **Self-hosted document management for people who want less paper, ngl.**

Folium has been renamed to lesspaper-ngl.

lesspaper-ngl gives you a searchable, organised home for your documents with local OCR, structured filing, full-text search, and human-controlled ingestion — for homelabs, NAS-backed servers, and private Docker deployments. Add embeddings and an LLM if you want semantic search, filing suggestions, and **Ask lesspaper-ngl** — or run the entire document-management workflow without AI.


<p align="center">
  <img src="assets/login.png" alt="lesspaper-ngl Login" width="1000">
</p>

**Document management first. RAG and AI second.** Search retrieves evidence; Ask generates answers from that evidence.

[![Release](https://img.shields.io/github/v/release/brocxftw/lesspaper-ngl?include_prereleases\&label=release)](https://github.com/brocxftw/lesspaper-ngl/releases)
[![License](https://img.shields.io/github/license/brocxftw/lesspaper-ngl)](LICENSE)
[![Container](https://img.shields.io/badge/container-GHCR-2496ED?logo=docker\&logoColor=white)](https://github.com/brocxftw/lesspaper-ngl/pkgs/container/lesspaper-ngl-backend)
![Platform](https://img.shields.io/badge/platform-linux%2Famd64-lightgrey)

---

## Why lesspaper-ngl?

Most document-management systems solve storage and organisation. AI document tools often solve a different problem entirely — and require handing your documents to a model before they become useful.

lesspaper-ngl is built around a simpler idea:

* Store and organise documents
* Extract text and OCR scans locally
* Search with PostgreSQL full-text search
* File documents into folders and tags
* Review metadata before committing it
* Manage multiple users and quotas
* Archive, trash, restore, and purge documents

AI capabilities sit **on top** of that foundation, with support for both local providers and OpenAI-compatible APIs (cloud or self-hosted).

When configured, lesspaper-ngl can additionally:

* Suggest titles, folders, tags, document types, and correspondents
* Generate chunk embeddings
* Add semantic and hybrid retrieval
* Answer questions over your documents with **Ask lesspaper-ngl**
* Return citations back to the supporting evidence

No AI provider? lesspaper-ngl remains a document-management system.

---

## At a glance

| Features            | lesspaper-ngl                                        |
| ------------------- | --------------------------------------------- |
| **Deployment**      | Self-hosted Docker Compose                    |
| **Storage**         | Local disk, bind mounts, host-mounted NAS/NFS |
| **Database**        | PostgreSQL + pgvector                         |
| **OCR**             | Local PaddleOCR PP-OCRv6                      |
| **Keyword search**  | PostgreSQL full-text search                   |
| **Semantic search** | Optional embeddings                           |
| **AI providers**    | Local or remote, policy controlled            |
| **Filing**          | Human-controlled Inbox → Process workflow     |
| **Originals**       | Content-addressed SHA-256 storage             |
| **Users**           | Multi-user with owner isolation and quotas    |
| **API**             | FastAPI + OpenAPI                             |
| **MCP**             | Read-only document/search integration         |
| **Licence**         | GNU AGPL v3.0                                 |

---

# What lesspaper-ngl does

## 📥 Ingest and review

Documents can enter lesspaper-ngl through drag and drop or folder/individual files selection.

lesspaper-ngl then prepares them before they enter the final library:

```text
Upload / Consume
        ↓
Text extraction
        ↓
      OCR
        ↓
Optional AI suggestions
        ↓
      Inbox
        ↓
Human review
        ↓
     Process
        ↓
Final indexing
        ↓
Optional embeddings
        ↓
 Search / Ask
```

<p align="center">
  <img src="assets/ingestion_2.png" alt="lesspaper-ngl Login" width="1000">
</p>

The **Process** action is intentional.

OCR completing does not silently decide where a document belongs. AI suggestions remain suggestions until you accept them, and documents can be reviewed manually when AI is disabled.

Uploads that already have an explicit library destination can bypass the Inbox where appropriate.

---

## 🗂️ Organise your library

lesspaper-ngl treats organisation as first-class document metadata.

You can manage:

* Nested logical folders
* Tags
* Document types
* Correspondents
* Titles and notes
* Created and effective dates
* Archive serials
* Custom metadata
* Bulk move, tag, archive, trash, and restore actions


<p align="center">
  <img src="assets/library.png" alt="lesspaper-ngl Library" width="1000">
</p>


Logical folders do **not** physically move the stored original.

Original files live in content-addressed storage keyed by SHA-256, while folders and filing information remain database metadata.

That keeps storage predictable and lets lesspaper-ngl reorganise documents without constantly moving files around your filesystem.

---

## 🔎 Find documents quickly

lesspaper-ngl separates **finding evidence** from **asking AI about evidence**.

### Quick Search

Press:

```text
Ctrl + K
```

or:

```text
Cmd + K
```

to open Quick Search from anywhere in the application.

<p align="center">
  <img src="assets/search.png" alt="lesspaper-ngl Search" width="1000">
</p>


### Keyword search

Works without AI.

lesspaper-ngl uses PostgreSQL full-text search across document and page content so OCRed and extracted text remains searchable even with no embedding provider configured.

### Semantic search

When embeddings are configured, lesspaper-ngl can retrieve document chunks by meaning rather than exact wording.

### Hybrid search


lesspaper-ngl combines keyword and semantic retrieval using reciprocal rank fusion.

If semantic retrieval is unavailable, search can fall back to keyword retrieval rather than making the library unusable.

> **Search retrieves evidence. Ask lesspaper-ngl generates an answer from evidence.**

They are deliberately separate operations.

---

## ✨ Ask lesspaper-ngl

Ask questions against:

* The entire library
* A folder
* A folder and its descendants
* Selected documents
* The current document
* A frozen set of search results

lesspaper-ngl retrieves relevant document chunks first, then sends that evidence to the configured chat model.

<p align="center">
  <img src="assets/document-preview.png" alt="Document Preview" width="1000">
</p>

Answers are tied back to retrieved evidence using validated citations.

```text
Question
   ↓
Resolve scope
   ↓
Keyword / semantic retrieval
   ↓
Rank evidence
   ↓
Build bounded context
   ↓
Chat model
   ↓
Answer + citations
```

If the available evidence cannot support an answer, lesspaper-ngl can return an **insufficient evidence** result rather than pretending the library contains an answer.

Ask lesspaper-ngl currently focuses on a bounded, single-turn evidence workflow rather than behaving like a general-purpose chatbot.

---

## 🤖 AI — optional by design

lesspaper-ngl separates AI responsibilities rather than assuming one model must do everything.

<p align="center">
  <img src="assets/ai_features.png" alt="Document Preview" width="1000">
</p>

Providers can be assigned independently for:

* **Filing** — metadata and organisation suggestions
* **Embeddings** — semantic retrieval
* **Chat** — Ask lesspaper-ngl
* **Vision** — where configured

Providers may be local or remote depending on your deployment and privacy policy.

### Without AI

lesspaper-ngl still supports:

* Upload and consume
* Text extraction
* Local OCR
* Inbox review
* Manual filing
* Folder and tag organisation
* Chunk indexing
* Keyword search
* Library management
* Trash and retention

### With AI

You can add:

* Filing suggestions
* Embeddings
* Semantic search
* Hybrid search
* Ask lesspaper-ngl
* AI-assisted document understanding

lesspaper-ngl also distinguishes between provider claims such as **no training** or **zero retention** and privacy controls actually enforced by the application.

---

## 🔐 Privacy controls

lesspaper-ngl supports application-level privacy policies for AI workloads.

Deployment policies can control whether document content may be sent to remote providers, including separate controls for embeddings, Q&A, and vision workloads.

Typical modes include:

* **Local only** — document content stays with local AI providers
* **Private hybrid** — prefer local providers and permit remote use according to policy
* **Standard** — use configured providers subject to the configured controls

Remote-provider confirmation and blocking policies can be applied separately.

Self-hosting alone does not automatically make every configured AI provider private — lesspaper-ngl makes that boundary explicit.

---

## 📤 Share original documents

Documents can be shared directly from the viewer and document menus.

On browsers supporting the Web Share API, lesspaper-ngl hands the **original file** to the operating system's native share sheet — useful for sending a document through applications such as mail or messaging clients.

<p align="center">
  <img src="assets/share.png" alt="Share" width="1000">
</p>

Where native file sharing is unavailable, lesspaper-ngl falls back to downloading the original.

No third-party messaging integration or vendor API is required.

---

## 🧾 OCR built in

lesspaper-ngl uses local **PaddleOCR PP-OCRv6** for scanned PDFs and images.

Supported ingestion includes:

* PDFs with embedded text
* Scanned PDFs
* Images
* DOCX
* Plain text
* Markdown

OCR runs in the worker rather than requiring an external LLM service.

The OCR execution path is isolated so large OCR workloads do not permanently retain PaddleOCR model memory inside the long-running worker process.

---

## 🗄️ Storage that stays understandable

lesspaper-ngl uses three main filesystem concepts:

```text
/documents    persistent document storage
/consume      watched ingestion directory
/export       export destination
```

Originals are content-addressed:

```text
/documents/originals/{aa}/{sha256}.{ext}
```

This means the logical library hierarchy is independent of the physical blob location.

### NAS / NFS

Mount your NAS or NFS share on the Docker host, then bind-mount that host directory into lesspaper-ngl.

Keep PostgreSQL on local Docker volume storage.

See [`docs/architecture/storage.md`](docs/architecture/storage.md).

---

# Installation

The recommended deployment path uses the published GHCR images and the interactive installer.

## Interactive installer

Download the installer, review it, then run it:

```bash
curl -fsSL -o install-lesspaper-ngl.sh \
  https://github.com/brocxftw/lesspaper-ngl/releases/latest/download/install-lesspaper-ngl.sh

less install-lesspaper-ngl.sh

bash install-lesspaper-ngl.sh
```

`releases/latest` is the newest **stable** release. The installer can still list beta tags in the version picker after it starts.

The installer can:

* Check deployment prerequisites
* Configure lesspaper-ngl
* Set up storage
* Configure network exposure
* Select a published release
* Offer stable or beta releases where available
* Pull versioned GHCR images
* Create the Compose deployment
* Wait for lesspaper-ngl to become healthy
* Detect an existing installation and offer an update path

The default installation lives under:

```text
/opt/lesspaper-ngl
```

Fresh installs use `/opt/lesspaper-ngl`. Existing deployments under `/opt/folium` are still discovered and remain supported through the update path.

The installer also publishes `install-folium.sh` as an identical transition shim (same contents as `install-lesspaper-ngl.sh`).

Host management CLI (primary command `lesspaper-ngl`; `folium` remains a shim for one transition cycle):

```bash
lesspaper-ngl status
lesspaper-ngl start
lesspaper-ngl stop
lesspaper-ngl logs
lesspaper-ngl doctor
lesspaper-ngl update                 # newest beta (default)
```

Published images: `ghcr.io/brocxftw/lesspaper-ngl-backend` and `ghcr.io/brocxftw/lesspaper-ngl-web`.

Installer documentation:

[`docs/deployment/installer.md`](docs/deployment/installer.md)

---

## Pre-release / beta

lesspaper-ngl publishes GitHub **prereleases** (`vX.Y.Z-beta.N`). They do **not** replace `releases/latest` or the moving GHCR `latest` tag.

### Interactive

1. Download the installer from a prerelease tag (or use the stable installer and pick a **Beta** entry in the version menu):

```bash
# Replace the tag with a prerelease from
# https://github.com/brocxftw/lesspaper-ngl/releases
curl -fsSL -o install-lesspaper-ngl.sh \
  https://github.com/brocxftw/lesspaper-ngl/releases/download/v0.1.24-beta.5/install-lesspaper-ngl.sh

less install-lesspaper-ngl.sh
bash install-lesspaper-ngl.sh
```

2. In the version picker, choose the matching `vX.Y.Z-beta.N` (labelled **Beta**), or another listed beta.

### Non-interactive

From the host/CT shell (after the management CLI is installed):

```bash
lesspaper-ngl update                 # newest beta prerelease (default)
lesspaper-ngl update latest          # newest stable
lesspaper-ngl update v0.1.24-beta.5  # exact pin
```

Or run the installer directly:

```bash
# Fresh install of the newest prerelease
bash install-lesspaper-ngl.sh --noninteractive --version beta --json

# Or pin an exact prerelease
bash install-lesspaper-ngl.sh --noninteractive --version v0.1.24-beta.5 --json

# Update an existing install to the newest beta (secrets/bind kept)
bash install-lesspaper-ngl.sh --noninteractive --update --version beta --json
```

`--version` (and `LESSPAPER_NGL_VERSION` / `LESSPAPER_NGL_VERSION_TAG` in the process environment; legacy `FOLIUM_*` equivalents still accepted) overrides the version already recorded in `install-state.json` / `.env`.

If `lesspaper-ngl update` still says it is unavailable, re-run the installer once to refresh `/usr/local/bin/lesspaper-ngl` (and the `folium` shim).

### Manual Compose

Download Compose assets from the same prerelease tag (not `releases/latest`):

```bash
TAG=v0.1.24-beta.5   # example — use a real prerelease tag

curl -fsSL -o docker-compose.yml \
  "https://github.com/brocxftw/lesspaper-ngl/releases/download/${TAG}/docker-compose.yml"
curl -fsSL -o env.example \
  "https://github.com/brocxftw/lesspaper-ngl/releases/download/${TAG}/env.example"
```

Set `LESSPAPER_NGL_VERSION` to the tag **without** the leading `v` (for example `0.1.24-beta.5`). Prefer that pin over the moving GHCR `beta` image tag.

---

## Automation / non-interactive installation

The installer also supports a non-interactive path intended for repeatable deployment and automation.

Existing installations can be detected and updated while preserving secrets and storage configuration.

See the installer documentation for the supported command-line contract:

[`docs/deployment/installer.md`](docs/deployment/installer.md)

---

## Manual Docker Compose

Prefer to manage Compose yourself?

Download the **stable** release assets:

```bash
mkdir lesspaper-ngl
cd lesspaper-ngl

curl -fsSL -o docker-compose.yml \
  https://github.com/brocxftw/lesspaper-ngl/releases/latest/download/docker-compose.yml

curl -fsSL -o env.example \
  https://github.com/brocxftw/lesspaper-ngl/releases/latest/download/env.example

cp env.example .env
```

For a prerelease, download the same filenames from that tag’s release assets instead (see [Pre-release / beta](#pre-release--beta)).

Configure at minimum (canonical `LESSPAPER_NGL_*`; legacy `FOLIUM_*` still accepted during upgrades):

```text
LESSPAPER_NGL_SECRET_KEY
LESSPAPER_NGL_ENCRYPTION_KEY
POSTGRES_PASSWORD
LESSPAPER_NGL_ADMIN_PASSWORD
```

Create storage:

```bash
mkdir -p \
  data/documents \
  data/consume \
  data/export \
  data/paddleocr

sudo chown -R 1000:1000 \
  data/documents \
  data/consume \
  data/export \
  data/paddleocr
```

Then start lesspaper-ngl:

```bash
docker compose up -d
```

Open:

```text
http://localhost:9398
```

The bootstrap administrator configured in `.env` is created on the **first start only**.

OpenAPI:

```text
http://localhost:9398/docs
```

MCP:

```text
http://localhost:9398/mcp
```

The backend API port is not published directly unless you explicitly configure it.

Persistence names kept on purpose (do not rename mid-flight): Postgres role/database `folium`, Docker volume `folium_pgdata`, backup extension `.folium` / manifest `folium_version`, cookies `folium_session` / `folium_csrf`.

Full manual installation guide:

[`docs/deployment/install.md`](docs/deployment/install.md)

---

# Updating

## Host CLI (primary)

On the Docker host / CT where lesspaper-ngl is installed:

```bash
lesspaper-ngl update                 # newest beta prerelease (default)
lesspaper-ngl update latest          # newest stable
lesspaper-ngl update v0.1.24-beta.5  # exact pin
```

`lesspaper-ngl update` downloads a fresh release installer and runs the noninteractive update path (secrets, bind, ports, and storage paths are preserved). The `folium` CLI shim continues to work for one transition cycle.

If the CLI still reports that update is unavailable, refresh it once with the installer (below), then use `lesspaper-ngl update` afterward.

## Installer deployment

Re-run the installer:

```bash
curl -fsSL -o install-lesspaper-ngl.sh \
  https://github.com/brocxftw/lesspaper-ngl/releases/latest/download/install-lesspaper-ngl.sh

less install-lesspaper-ngl.sh

bash install-lesspaper-ngl.sh
```

When lesspaper-ngl detects the existing installation, choose **Update**, then pick the target release (stable or beta).

Your secrets and document storage remain in place while the selected release images are pulled and the stack is recreated.

Non-interactive update to newest stable or beta:

```bash
bash install-lesspaper-ngl.sh --noninteractive --update --version latest --json
bash install-lesspaper-ngl.sh --noninteractive --update --version beta --json
```

## Manual Compose deployment

Choose the version you want from [Releases](../../releases), set that release in `.env`, then:

```bash
docker compose pull
docker compose up -d
```

Do **not** use:

```bash
docker compose down -v
```

unless you explicitly intend to remove persistent Docker volumes.

The API applies database migrations during startup.

Verify the deployment:

```bash
curl -sS http://localhost:9398/health
```

Upgrade and rollback notes:

[`docs/deployment/upgrades.md`](docs/deployment/upgrades.md)

---

# Backup and restore

lesspaper-ngl can create full `.folium` backup bundles containing the state required to restore an installation. The `.folium` extension and `folium_version` manifest field are intentional persistence (not rebranded).

The current backup implementation focuses on full local backups rather than incremental or cloud-native backup strategies.

Fresh installations can use the restore workflow to recover an existing lesspaper-ngl deployment.

See:

[`docs/deployment/backup.md`](docs/deployment/backup.md)

For important deployments, lesspaper-ngl's built-in backup should still be part of a wider host/NAS backup strategy rather than your only copy of the data.

---

# MCP integration

lesspaper-ngl exposes a read-only MCP endpoint at:

```text
/mcp
```

Create an API token from:

```text
Settings → Profile
```

The MCP surface can be used by compatible external tools and agents to:

* Search evidence
* Search documents
* Read document content
* Browse folders

The MCP integration is intentionally read-only.

Ask lesspaper-ngl itself is not exposed as an MCP tool.

---

# Administration

lesspaper-ngl includes administration surfaces for:

* User profiles
* AI providers and workload assignments
* AI privacy controls
* Library settings
* User administration
* Storage and system information
* Backup and restore
* Application logs
* About and project information

Multi-user deployments include:

* Owner-isolated libraries
* Invites
* Storage quotas
* Monthly AI request quotas
* Administrator controls
* Administrator-assisted password reset

---

# Architecture

lesspaper-ngl is a Docker Compose application built around a deliberately conventional architecture:

```text
                     ┌──────────────┐
                     │   Browser    │
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │  web / nginx │
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │   FastAPI    │
                     │     API      │
                     └───┬──────┬───┘
                         │      │
                ┌────────▼─┐  ┌─▼──────────────┐
                │PostgreSQL│  │ Document files │
                │+ pgvector│  │ / NAS storage  │
                └─────┬────┘  └────────────────┘
                      │
                ┌─────▼─────┐
                │ Jobs table │
                └─────┬─────┘
                      │
                ┌─────▼─────┐
                │   Worker   │
                │ OCR / index│
                │ / embed    │
                └────────────┘
```

The database-backed worker queue handles long-running document work such as OCR, indexing, embeddings, thumbnails, and metadata suggestions.

Architecture documentation:

[`docs/architecture/overview.md`](docs/architecture/overview.md)

---

# Health and operations

Application health endpoints include:

```text
/health
/health/database
/health/storage
```

AI provider availability is intentionally separate from core application health.

An unavailable LLM should not make a functioning document-management deployment appear dead.

The Jobs workspace exposes background work and cancellation controls, while application logs are persisted in PostgreSQL for inspection through the UI.

---

# Development

lesspaper-ngl consists of:

```text
backend/     FastAPI, workers, domain services, Alembic, tests
frontend/    React + TypeScript application
docker/      Container definitions and nginx
installer/   Whiptail installer and management tooling
docs/        Architecture, development and operations documentation
```

Run the project test suite with:

```bash
make test
```

This covers the backend, frontend build/tests, and installer helpers.

Start here for development:

[`docs/development/local-development.md`](docs/development/local-development.md)

Contributing:

[`docs/development/contributing.md`](docs/development/contributing.md)

---

# Documentation

The root README is intentionally the project's front door.

The detailed source of truth lives under [`docs/`](docs/README.md).

| Area               | Documentation                                                |
| ------------------ | ------------------------------------------------------------ |
| Architecture       | [`docs/architecture/`](docs/architecture/overview.md)        |
| Backend            | [`docs/backend/`](docs/backend/overview.md)                  |
| Frontend           | [`docs/frontend/`](docs/frontend/overview.md)                |
| Deployment         | [`docs/deployment/`](docs/deployment/overview.md)            |
| Development        | [`docs/development/`](docs/development/local-development.md) |
| Product vocabulary | [`ubiquitous-language.md`](ubiquitous-language.md)           |

A useful rule for the project is:

```text
CODE → docs/ → README.md
```

The README should explain lesspaper-ngl.

The documentation should explain how lesspaper-ngl works.

---

# Release channels

lesspaper-ngl is currently a **pre-1.0 project** and is evolving quickly.

Published GitHub releases are the deployment boundary. Operators should run versioned GHCR images rather than building the current `main` branch for production use.

| Channel | GitHub | GHCR image tags | Installer |
|---------|--------|-----------------|-----------|
| Stable | `releases/latest`, tags `vX.Y.Z` | `X.Y.Z`, `X.Y`, `latest` | `--version latest` or a stable pin |
| Beta / prerelease | Prerelease tags `vX.Y.Z-beta.N` | `X.Y.Z-beta.N`, moving `beta` | `--version beta` or a beta pin |

Prereleases do not move `latest`. Prefer pinning `vX.Y.Z-beta.N` / `LESSPAPER_NGL_VERSION=X.Y.Z-beta.N` over the moving `beta` image tag.

Install and update steps: [Pre-release / beta](#pre-release--beta).

See:

[GitHub Releases](../../releases)

---

# Current limitations

lesspaper-ngl is actively developed. Important limitations currently include:

* Published images currently target **linux/amd64**
* ARM deployments are not yet a supported release target
* `/export` is mounted but document export functionality remains limited
* Backup V1 uses full local `.folium` bundles rather than incremental/cloud backups
* Password reset is administrator-assisted; SMTP recovery is not currently provided
* Browser end-to-end test coverage is still limited
* Multi-turn conversational Ask is not yet the primary Ask workflow
* Database migrations are forward-moving; reverting an image does not automatically reverse schema migrations
* Semantic capabilities depend on embedding-provider availability and coverage
* AI quality depends on the models and context limits configured by the operator

For release-readiness details:

[`docs/deployment/production-readiness.md`](docs/deployment/production-readiness.md)

---

# Licence

lesspaper-ngl is licensed under the [GNU Affero General Public License v3.0](LICENSE).

The project uses PyMuPDF for PDF text extraction and rendering, and the project licence reflects the resulting copyleft requirements.

See the dependency and licensing notes in:

[`docs/deployment/production-readiness.md`](docs/deployment/production-readiness.md)

This is not legal advice.

---

# Acknowledgements

lesspaper-ngl is built with:

* FastAPI
* PostgreSQL
* pgvector
* React
* PaddleOCR
* PyMuPDF
* nginx
* Docker

Its operational shape is inspired by mature self-hosted document-management projects such as Paperless-ngx, while lesspaper-ngl remains an independent implementation rather than a Paperless-ngx fork.

