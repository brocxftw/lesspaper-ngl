# Repository structure

```text
backend/          FastAPI application, Alembic, pytest
frontend/         Vite React SPA
docker/           Dockerfiles, nginx, backend entrypoint
installer/        Whiptail TUI installer, bootstrap, `lesspaper_ngl` CLI
docs/             Engineering documentation (this tree)
.github/          CI workflow only
data/             Local bind-mount placeholders (gitignored content)
```

Root files: `docker-compose.yml`, `.env.example`, `Makefile`, `ubiquitous-language.md`, `README.md`.

**Backend layout:** `src/lesspaper_ngl/{api,ai,auth,core,db,models,ocr,search,services,storage,workers}`.

**Frontend layout:** `src/features/*` (pages), `src/components/*` (domain + ui), `src/lib/api`.

Do not put secrets in git (`.env` and `.env.*` are gitignored; only `.env.example` is tracked). Product vocabulary: root `ubiquitous-language.md`. Engineering docs: `docs/`.
