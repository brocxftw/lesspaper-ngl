# Environment variables

Verified from `lesspaper_ngl.core.config.Settings`, `lesspaper_ngl.core.version`, Compose, and Dockerfiles.

Canonical env prefix is `LESSPAPER_NGL_`. Legacy `FOLIUM_*` keys are still accepted by the app and Compose during upgrades. Cookie defaults remain `folium_session` / `folium_csrf`; Postgres role/database default to `folium`.

Legend: **Required** means “must be set to a non-default secret in any real deployment”, not “process will crash if unset” (many fields have insecure code defaults). Public `.env.example` leaves secrets empty so Compose fails closed on `POSTGRES_PASSWORD`.

## Application (`Settings`)

| Variable | Required | Default | Service | Purpose | Sensitive |
|----------|----------|---------|---------|---------|-----------|
| `LESSPAPER_NGL_SECRET_KEY` | Yes (prod) | `dev-secret-change-me` | api, worker | Session/token material | Yes |
| `LESSPAPER_NGL_ENCRYPTION_KEY` | Yes (prod) | `dev-encryption-key-change-me` | api, worker | Fernet for provider API keys | Yes |
| `LESSPAPER_NGL_ENV` | No | `development` | api, worker | `production` disables Vite-style reload; affects Secure cookies with HTTPS origin | No |
| `LESSPAPER_NGL_LOG_LEVEL` | No | `INFO` | api, worker | Log level | No |
| `LESSPAPER_NGL_HOST` | No | `0.0.0.0` | api (local uvicorn) | Bind host; Compose uvicorn hard-codes 0.0.0.0 | No |
| `LESSPAPER_NGL_PORT` | No | `8000` | api (local uvicorn) | Compose uvicorn hard-codes 8000 | No |
| `LESSPAPER_NGL_ADMIN_USERNAME` | First boot | `admin` | api | Bootstrap / lookup admin | No |
| `LESSPAPER_NGL_ADMIN_PASSWORD` | First boot | `changeme` | api | Bootstrap only | Yes |
| `ALLOW_REGISTRATION` | No | code `true`; example `false` | api | Open registration | No |
| `DEFAULT_STORAGE_QUOTA_BYTES` | No | `null` | api | Default quota for new users | No |
| `DEFAULT_AI_MONTHLY_REQUEST_QUOTA` | No | `null` | api | Default AI quota | No |
| `PASSWORD_RESET_TOKEN_TTL_HOURS` | No | `1` | api | Reset link TTL | No |
| `MAX_AVATAR_SIZE_MB` | No | `2` | api | Avatar cap | No |
| `CONSUME_OWNER_USERNAME` | No | `null` (earliest admin) | worker | Consume ingest owner | No |
| `DATABASE_URL` | Yes | localhost:5433 async URL | api, worker | SQLAlchemy async; **Compose overwrites** from `POSTGRES_*` | Yes |
| `DATABASE_URL_SYNC` | Yes | localhost:5433 sync URL | migrations / worker healthcheck | Sync URL; **Compose overwrites** | Yes |
| `DOCUMENTS_PATH` | Yes in containers | `/documents` | api, worker | Library storage root | No |
| `CONSUME_PATH` | Yes in containers | `/consume` | api, worker | Consume root | No |
| `EXPORT_PATH` | Yes in containers | `/export` | api, worker | Export root | No |
| `BACKUPS_PATH` | Yes in containers | `/backups` | api, worker | Backup repository root | No |
| `LESSPAPER_NGL_DOCUMENTS_HOST_SOURCE` | No | `null` | api | UI label for host path | No |
| `MAX_UPLOAD_SIZE_MB` | No | `100` | api | Upload cap | No |
| `ALLOWED_MIME_TYPES` | No | pdf/png/jpeg/txt/md/docx | api | MIME allow-list | No |
| `OCR_LANGUAGE` | No | `eng` | worker | Mapped to Paddle language | No |
| `OCR_ENABLED` | No | `true` | worker | Dedicated OCR jobs | No |
| `OCR_DPI` | No | `150` | worker | PDF page render DPI for OCR (lower = less RAM) | No |
| `OCR_IN_PROCESS` | No | `false` | worker | Load Paddle in the worker process (tests/debug); production uses a subprocess | No |
| `OCR_SUBPROCESS_TIMEOUT_SECONDS` | No | `3600` | worker | Soft timeout for one OCR child process | No |
| `JOB_CONCURRENCY` | No | `1` | worker | In-process job slots; OCR also takes an exclusive gate | No |
| `CONSUME_POLL_INTERVAL_SECONDS` | No | `5` | worker | Consume poll / stability wait | No |
| `JOB_POLL_INTERVAL_SECONDS` | No | `2` | worker | Main loop sleep | No |
| `JOB_STALE_RUNNING_SECONDS` | No | `600` | worker | Requeue stale RUNNING | No |
| `JOB_LOCK_HEARTBEAT_SECONDS` | No | `60` | worker | Lock heartbeat | No |
| `TRASH_RETENTION_DAYS` | No | `30` | worker, api | Purge window | No |
| `TRASH_PURGE_INTERVAL_SECONDS` | No | `3600` | worker | Purge cadence | No |
| `APPLICATION_LOG_RETENTION_DAYS` | No | `30` | api | Log retention 1–365 | No |
| `AI_PRIVACY_MODE` | No | `local_only` | api bootstrap | Seed `ai_settings` only | No |
| `AI_PROFILE` | No | `lightweight` | api bootstrap | Seed profile | No |
| `AI_ALLOW_REMOTE_EMBEDDINGS` | No | `false` | api bootstrap | Seed flag | No |
| `AI_ALLOW_REMOTE_QA` | No | `false` | api bootstrap | Seed flag | No |
| `AI_ALLOW_REMOTE_VISION` | No | `false` | api bootstrap | Seed flag | No |
| `AI_WARN_BEFORE_REMOTE` | No | `true` | api bootstrap | Seed flag | No |
| `SESSION_COOKIE_NAME` | No | `folium_session` | api | Session cookie | No |
| `SESSION_TTL_HOURS` | No | `168` | api | Session lifetime | No |
| `CSRF_COOKIE_NAME` | No | `folium_csrf` | api | Must match SPA (`folium_csrf` hard-coded) | No |
| `FRONTEND_ORIGIN` | Prod | `http://localhost:9398` | api | Comma-separated CORS + MCP origins | No |
| `LESSPAPER_NGL_SECURE_COOKIES` | No | `false` | api | Force `Secure` on session/CSRF cookies (e.g. HTTPS reverse proxy with HTTP LAN origin in list) | No |
| `LESSPAPER_NGL_BUILD_REVISION` | Images | `null` | api | About page; baked into published images | No |
| `LESSPAPER_NGL_BUILD_DATE` | Images | `null` | api | About page; baked into published images | No |
| `LESSPAPER_NGL_REPOSITORY_URL` | Images | GitHub URL in images | api | About links | No |
| `LESSPAPER_NGL_ISSUES_URL` | Images | GitHub issues in images | api | About links | No |
| `LESSPAPER_NGL_DOCS_URL` | Images | docs README in images | api | About links | No |
| `LESSPAPER_NGL_RELEASES_URL` | Images | GitHub releases in images | api | About links | No |
| `LESSPAPER_NGL_LICENSE_URL` | Images | LICENSE in images | api | About links | No |

## Version (not on Settings)

| Variable | Required | Default | Service | Purpose | Sensitive |
|----------|----------|---------|---------|---------|-----------|
| `LESSPAPER_NGL_VERSION` | Image tag + runtime | `latest` in repo Compose; baked in images | compose, api | Image tag **and** `/health` version | No |

Leading `v` is stripped (`v0.1.16` → `0.1.16`).

## Compose / host only

| Variable | Required | Default | Service | Purpose | Sensitive |
|----------|----------|---------|---------|---------|-----------|
| `LESSPAPER_NGL_DOCUMENTS_HOST` | No | `./data/documents` | compose | Host bind source | No |
| `LESSPAPER_NGL_CONSUME_HOST` | No | `./data/consume` | compose | Host bind source | No |
| `LESSPAPER_NGL_EXPORT_HOST` | No | `./data/export` | compose | Host bind source | No |
| `LESSPAPER_NGL_BACKUPS_HOST` | No | `./data/backups` | compose | Backup repository bind | No |
| `LESSPAPER_NGL_PADDLE_CACHE_HOST` | No | `./data/paddleocr` | compose | OCR cache bind | No |
| `POSTGRES_USER` | No | `folium` | `db` + URL interpolation | Database role | No |
| `POSTGRES_PASSWORD` | **Yes** | none (`:?`) | `db` + URL interpolation | Database password | Yes |
| `POSTGRES_DB` | No | `folium` | `db` + URL interpolation | Database name | No |

Do not put `@ : / # ?` in `POSTGRES_PASSWORD` (it is interpolated into a URL). Prefer `openssl rand -hex 24`.

## Dockerfile / Paddle (process env in image)

`PADDLE_PDX_CACHE_HOME`, `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK`, `PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT`, `FLAGS_use_mkldnn` — OCR runtime, not lesspaper-ngl Settings.
