# Production readiness

Audit of public **image-based** install after GHCR distribution work.

Intended experience:

```text
download docker-compose.yml
download env.example
configure
docker compose up -d
```

---

## Classification

```text
Ready with caveats
```

**Justification:** Operators can install with the interactive installer, or from GitHub Release Compose + `env.example`, and pull `ghcr.io/brocxftw/lesspaper-ngl-backend` / `lesspaper-ngl-web` without cloning or building lesspaper-ngl. API and worker share one backend image. Secrets are not shipped as usable production passwords. Postgres is not published on the host. Registration defaults off in the example. AI-down does not fail `/health`. Remaining caveats: **linux/amd64 only**, GHCR packages must be set **public** after first publish, first OCR downloads models, no browser e2e suite, Alembic is forward-only, and anonymous GHCR pull is unverified until the first tagged publish on `main`.

Until the first `v*` tag after merge succeeds, packages may not exist yet — the **workflow is present**; images are not automatically backfilled for older tags.

---

## Addressed vs remaining

### Addressed

| Item | State |
|------|--------|
| Published image workflow | `.github/workflows/publish-images.yml` on `v*` |
| Public Compose `image:` | `docker-compose.yml` |
| Contributor `build:` | `compose.dev.yaml` + Makefile |
| `LESSPAPER_NGL_VERSION` at image build | Dockerfile ARG/ENV + OCI labels |
| Postgres password | `POSTGRES_PASSWORD` required interpolation |
| `group_add: 10000` | Removed from public Compose |
| DB host port | Dev overlay only |
| CI `ruff \|\| true` | Removed; ruff gates CI |
| Worker healthcheck | Heartbeat + Compose check + `GET /health/worker` |
| Backup / upgrade docs | [backup.md](backup.md), [upgrades.md](upgrades.md) |
| Registration example | `ALLOW_REGISTRATION=false` |

### Caveats (honest remaining risk)

| Finding | Notes |
|---------|--------|
| GHCR visibility | One-time maintainer: make packages public |
| No images until first tag | Existing `v0.1.x` tags were not published |
| ARM | Unsupported / untested (Paddle wheels) |
| Paddle index | CPU wheels from Paddle’s package index |
| No Playwright e2e | Smoke is Compose `/health` |
| CSRF cookie name | Still hard-coded in the SPA |
| `/export` unused | Mount without export feature |
| Schema rollback | Not supported; restore from backup |
| Secure cookies | Only if origin is https and env is not development |

---

## Can an external user…?

| Question | After this work |
|----------|-----------------|
| 1. Obtain lesspaper-ngl | Yes — Release assets + GHCR (once packages are public and a tag has published) |
| 2. Configure it | Yes — `.env`; Postgres password required |
| 3. Start it | Yes — `docker compose up -d` pulls images |
| 4. Retain data across upgrades | Yes for volume + binds; migrations run on api start |
| 5. Update it | `LESSPAPER_NGL_VERSION=…` then `pull` + `up -d` |
| 6. Diagnose failed startup | Logs + `/health`; worker healthcheck and `/health/worker` |
| 7. Use without AI | **Yes** |
| 8. Back up persistent data | Documented; no first-class backup tool |

---

## Dependency and licence notes (not legal advice)

Sources: package metadata / upstream licence files commonly published with these projects. **Maintainer review recommended** before any public distribution.

| Dependency | Purpose | Detected licence | Source of licence info | Review? |
|------------|---------|------------------|------------------------|---------|
| FastAPI / Starlette / Pydantic | API | MIT | PyPI classifiers / upstream LICENSE | Routine |
| Uvicorn | Server | BSD-3 | Upstream | Routine |
| SQLAlchemy / Alembic / asyncpg / psycopg | DB | MIT | Upstream | Routine |
| pgvector (extension + python) | Vectors | PostgreSQL Licence | Upstream README | Routine |
| PostgreSQL | Database | PostgreSQL Licence | postgresql.org | Routine |
| Argon2-cffi / cryptography | Auth/secrets | MIT / Apache-2.0+BSD | Upstream | Routine |
| httpx | AI HTTP | BSD-3 | Upstream | Routine |
| PyMuPDF (`pymupdf`) | PDF text/render | **AGPL-3.0** (typical PyPI) | PyPI / Artifex terms | **Yes — copyleft** |
| python-docx | DOCX | MIT | Upstream | Routine |
| Pillow | Images | HPND-derived | Upstream | Routine |
| PaddleOCR / PaddlePaddle | OCR | Apache-2.0 (typical) | Paddle GitHub LICENSE | Confirm CPU wheel terms |
| tiktoken | Token counts | MIT | Upstream | Routine |
| bleach | HTML sanitize | Apache-2.0 | Upstream | Routine |
| React / Vite / TanStack Query | SPA | MIT | npm | Routine |
| Tailwind CSS | CSS | MIT | npm | Routine |
| Radix UI | Primitives | MIT | npm | Routine |
| pdfjs-dist | PDF viewer | Apache-2.0 | Mozilla | Routine |
| nginx | `web` image | BSD-2-like | nginx.org | Routine |
| Node / Python base images | Runtime | Various | Image OS | Routine |

lesspaper-ngl’s project licence is **GNU AGPL v3.0** (`LICENSE` at the repository root), chosen to align with PyMuPDF’s typical AGPL-3.0 terms. That does **not** replace review of other dependency licences (Paddle wheels, base images). This is not legal advice.
