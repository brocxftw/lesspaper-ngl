# Testing

## Backend

```bash
cd backend
.venv/bin/pytest -q
# Makefile: make backend-test
```

- **Unit:** `tests/unit/` — chunking, privacy gate, jobs requeue, RAG helpers, OCR mocks, etc.
- **Integration:** `tests/integration/` — HTTP + Postgres (`folium_test` in CI). Requires pgvector Postgres (CI service on 5433).
- **Eval:** `tests/eval/` — filing sample coverage / histograms; not a full quality eval harness.
- Marker `live_ai`: optional real OpenAI-compatible endpoint (`LESSPAPER_NGL_LIVE_AI=1`).

CI installs `.[dev]` **without** `ocr`; Paddle is mocked.

Ruff/mypy configured in `pyproject.toml`. CI runs `ruff check` as a **gate**.

## Frontend

```bash
cd frontend
npm test              # vitest run
npm run build         # tsc -b && vite build
```

Mostly unit tests for Inbox helpers, readiness, citations, a few component tests. **No Playwright/e2e** in-repo.

## Compose

```bash
cp .env.example .env
# set POSTGRES_PASSWORD and secrets
docker compose -f docker-compose.yml config
docker compose -f docker-compose.yml -f compose.dev.yaml config
```

CI validates Compose interpolation and installer helpers (ShellCheck + `installer/tests/run.sh`). Image publish workflow builds amd64 images and smokes `GET /health`.

## Installer

```bash
bash installer/tests/run.sh
# optional throwaway Compose smoke (non-8080 port, dedicated project):
bash installer/tests/smoke.sh
```

See [installer](../deployment/installer.md) for the manual matrix that is not fully automated.

## Gaps (Confirmed)

- No end-to-end browser tests
- OCR extra untested in CI against real Paddle
- Anonymous GHCR pull is only proven after the first tagged publish
