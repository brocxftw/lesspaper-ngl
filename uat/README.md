# lesspaper-ngl UAT

This is a repeatable, deterministic UAT loop: Playwright drives the browser; authenticated API helpers prepare data and wait for durable product state; the reporter collects evidence, classifies failures, writes reports, and can draft or safely publish GitHub issues.

## Audit and architecture

The frontend is React/Vite and uses cookie + CSRF authentication. The backend is FastAPI with Postgres-backed asynchronous OCR/indexing workers. Useful stable contracts are `/health`, `/health/worker`, `/api/about`, `/api/documents`, `/api/jobs`, `/api/search`, `/api/logs`, and `/api/ai/capabilities`. Docker Compose starts `api`, `worker`, `web`, and `db`; `api` and `worker` health checks make worker availability observable. Existing pytest integration tests cover API contracts, and `scripts/uat-mcp.sh` supplied the initial upload/process/search flow.

Run `npm install` in `frontend` once, then install Chromium with `cd frontend && npx playwright install --with-deps chromium` (or provision the listed system libraries in your base image). Start a local stack and run:

```bash
./scripts/run-uat.sh --issues=draft --ai=disabled
./scripts/run-uat.sh --journey=UAT-030 --headed
./scripts/run-uat.sh --issues=auto
```

Set `UAT_ORIGIN`, `UAT_USERNAME`, and `UAT_PASSWORD` for a non-default target. Each run uses an existing authenticated UAT account; it only creates run-named folders and fixture documents. Avoid pointing it at personal production data.

The AI-disabled golden suite implements login/logout, upload/Preflight, manual filing/Process, Library state, keyword evidence search, Trash, and Restore. `plain-text-document.txt` is synthetic and contains the known query `blue-orchid-741`. With `--ai=enabled`, the suite additionally probes configured capabilities and exercises filing suggestions, Semantic ready retrieval, the Evidence-search/chat boundary, Ask citations, and insufficient-evidence handling. A missing indexing, embedding, or chat capability is reported as an explicit skip; it is never a core UAT failure. OCR/scanned-PDF, mobile viewer, and hybrid retrieval remain future journeys.

Reports are written to `uat/reports/<run-id>/summary.{md,json}`. On failure Playwright writes screenshot/trace/video and the test fixture adds browser console and failed-network evidence under `uat/artifacts/<run-id>/`. For an authenticated administrator it also captures a bounded, API-redacted one-hour window of backend and worker structured logs; unavailable log access never hides the original failure.

`--issues=off` suppresses drafts; `draft` (default) writes GitHub-ready Markdown only; `auto` requires an authenticated `gh`, searches open issues for the UAT ID, and creates only blocker/critical/high `APPLICATION_DEFECT` findings without a duplicate. Infrastructure, locator/test, skipped, and unknown outcomes do not publish. Release gate: critical/blocker application defect = HOLD; other failures = REVIEW; otherwise PASS.

To add a journey, add its intent to `journeys/golden.yml`, implement deterministic assertions in `tests`, use `waitForDocument` rather than sleeps, and verify it manually once before treating it as golden.
