"""Shared pytest fixtures for lesspaper-ngl backend tests."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ---------------------------------------------------------------------------
# Environment — must be set before any lesspaper_ngl imports
# ---------------------------------------------------------------------------

_TEST_ROOT = Path(__file__).resolve().parent
_FIXTURES_DIR = _TEST_ROOT / "fixtures"

# Force test configuration (do not inherit developer shell/.env values).
os.environ["LESSPAPER_NGL_ENV"] = "test"
os.environ["LESSPAPER_NGL_SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["LESSPAPER_NGL_ENCRYPTION_KEY"] = "test-encryption-key-for-pytest"
os.environ["LESSPAPER_NGL_ADMIN_USERNAME"] = "admin"
os.environ["LESSPAPER_NGL_ADMIN_PASSWORD"] = "testpass"
os.environ["FRONTEND_ORIGIN"] = "http://test"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://folium:folium@localhost:5433/folium_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql+psycopg://folium:folium@localhost:5433/folium_test"
os.environ["OCR_ENABLED"] = "false"
# Unit tests mock Paddle in-process; production default is subprocess OCR.
os.environ["OCR_IN_PROCESS"] = "true"
os.environ["JOB_CONCURRENCY"] = "1"

from lesspaper_ngl.bootstrap import bootstrap  # noqa: E402
from lesspaper_ngl.core.config import get_settings  # noqa: E402
from lesspaper_ngl.db.session import Base, dispose_engine, get_session_factory  # noqa: E402
from lesspaper_ngl.main import app  # noqa: E402
from lesspaper_ngl.models import Job, JobType  # noqa: E402
from lesspaper_ngl.workers.processor import process_indexing, process_text_extraction  # noqa: E402

get_settings.cache_clear()

_db_lock = asyncio.Lock()

_TRUNCATE_TABLES = (
    "application_logs",
    "ai_model_assignments",
    "ai_usage",
    "ai_suggestions",
    "document_tags",
    "document_chunks",
    "document_pages",
    "documents",
    "backup_records",
    "backup_settings",
    "jobs",
    "sessions",
    "api_tokens",
    "password_reset_requests",
    "invites",
    "tags",
    "document_types",
    "correspondents",
    "ai_settings",
    "ai_providers",
    "folders",
    "library_activity_counters",
    "users",
    "app_settings",
)


def _apply_storage_paths(base: Path) -> None:
    docs = base / "documents"
    consume = base / "consume"
    export = base / "export"
    backups = base / "backups"
    for path in (docs, consume, export, backups):
        path.mkdir(parents=True, exist_ok=True)
    os.environ["DOCUMENTS_PATH"] = str(docs)
    os.environ["CONSUME_PATH"] = str(consume)
    os.environ["EXPORT_PATH"] = str(export)
    os.environ["BACKUPS_PATH"] = str(backups)
    get_settings.cache_clear()


async def _init_schema() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _truncate_and_bootstrap() -> None:
    async with _db_lock:
        await dispose_engine()
        factory = get_session_factory()
        async with factory() as session:
            tables = ", ".join(_TRUNCATE_TABLES)
            await session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
            await bootstrap(session)
            # Tests exercise a ready instance; first-run setup is covered separately.
            from lesspaper_ngl.auth import service as auth_service
            from lesspaper_ngl.bootstrap import ensure_ai_settings
            from lesspaper_ngl.models import InstanceState
            from lesspaper_ngl.services import folders as folder_service
            from lesspaper_ngl.services import instance_state as instance_state_service

            admin = await auth_service.ensure_admin_user(session)
            await folder_service.ensure_system_folders(session, admin.id)
            await ensure_ai_settings(session)
            await instance_state_service.ensure_installation_id(session)
            await instance_state_service.set_instance_state(session, InstanceState.READY)
            await session.commit()
        await dispose_engine()


async def login(client: AsyncClient) -> str:
    """Log in as admin and attach CSRF header; return csrf token."""
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "testpass"},
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = csrf
    return csrf


async def _run_extraction_pipeline(session: AsyncSession, document_id: uuid.UUID) -> None:
    """Run text extraction and indexing jobs synchronously in tests.

    Indexing is no longer chained from extraction (Inbox Process gate), so tests
    that need a fully searchable document enqueue indexing explicitly here.
    """
    from sqlalchemy import select

    from lesspaper_ngl.services.jobs import enqueue_job

    extract_job = (
        await session.execute(
            select(Job).where(
                Job.document_id == document_id,
                Job.job_type == JobType.TEXT_EXTRACTION,
            )
        )
    ).scalar_one()
    await process_text_extraction(session, extract_job)

    index_job = (
        await session.execute(
            select(Job).where(
                Job.document_id == document_id,
                Job.job_type == JobType.INDEXING,
            )
        )
    ).scalar_one_or_none()
    if index_job is None:
        index_job = await enqueue_job(
            session,
            job_type=JobType.INDEXING,
            document_id=document_id,
            priority=40,
        )
    await process_indexing(session, index_job)
    await session.commit()


# ---------------------------------------------------------------------------
# Session-scoped setup (sync wrapper avoids cross-loop engine issues)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def storage_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("folium_storage")
    _apply_storage_paths(base)
    return base


@pytest.fixture(scope="session")
def _schema_initialized(storage_root: Path) -> None:
    del storage_root
    get_settings.cache_clear()

    async def _setup() -> None:
        await dispose_engine()
        await _init_schema()
        await _truncate_and_bootstrap()

    asyncio.run(_setup())


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session(_schema_initialized: None) -> AsyncGenerator[AsyncSession]:
    """Provide a DB session; truncate all tables before each test."""
    await _truncate_and_bootstrap()
    factory = get_session_factory()
    async with factory() as session:
        yield session
        try:
            await session.rollback()
        except Exception:
            # Restore terminates other DB backends; the fixture connection may already be gone.
            pass


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    storage_root: Path,
    _schema_initialized: None,
) -> AsyncGenerator[AsyncClient]:
    """Unauthenticated HTTP client against the FastAPI app."""
    del db_session
    _apply_storage_paths(storage_root)
    await dispose_engine()
    get_settings.cache_clear()

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    await dispose_engine()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Authenticated client with CSRF header set."""
    await login(client)
    return client


@pytest_asyncio.fixture
async def guest_client(client: AsyncClient) -> AsyncGenerator[AsyncClient]:
    """Separate cookie jar; lifespan is already running via `client`."""
    del client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_txt_bytes() -> bytes:
    return (_FIXTURES_DIR / "sample.txt").read_bytes()


@pytest.fixture
def sample_txt_path(sample_txt_bytes: bytes, tmp_path: Path) -> Path:
    path = tmp_path / "sample.txt"
    path.write_bytes(sample_txt_bytes)
    return path


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a minimal PDF containing searchable text via PyMuPDF."""
    import fitz

    path = tmp_path / "lppsa-refinance.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "LPPSA refinance RM 420000 tenure 25 years monthly instalment RM 2180.",
    )
    doc.save(str(path))
    doc.close()
    return path


@pytest_asyncio.fixture
async def uploaded_txt_doc(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    sample_txt_path: Path,
) -> dict:
    """Upload sample.txt and run text extraction + indexing."""
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert response.status_code == 201, response.text
    doc = response.json()
    await _run_extraction_pipeline(db_session, uuid.UUID(doc["id"]))
    return doc


@pytest.fixture
def run_extraction(db_session: AsyncSession) -> Callable:
    """Return async helper to process extraction + indexing for a document."""

    async def _runner(document_id: uuid.UUID) -> None:
        await _run_extraction_pipeline(db_session, document_id)

    return _runner


@pytest_asyncio.fixture
async def restore_storage_paths(storage_root: Path) -> AsyncGenerator[None]:
    """Restore writable storage paths after tests that mutate env paths."""
    yield
    _apply_storage_paths(storage_root)
    await dispose_engine()
