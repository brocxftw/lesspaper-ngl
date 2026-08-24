"""lesspaper-ngl application settings."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env(*names: str) -> AliasChoices:
    """Prefer canonical LESSPAPER_NGL_* names; accept legacy FOLIUM_* during upgrades."""
    return AliasChoices(*names)


class PrivacyMode(StrEnum):
    LOCAL_ONLY = "local_only"
    PRIVATE_HYBRID = "private_hybrid"
    STANDARD = "standard"


class AIProfile(StrEnum):
    LIGHTWEIGHT = "lightweight"
    BALANCED = "balanced"
    QUALITY = "quality"
    CUSTOM = "custom"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        # Explicit environment variables always win over env files.
    )

    secret_key: str = Field(default="dev-secret-change-me", validation_alias=_env("LESSPAPER_NGL_SECRET_KEY", "FOLIUM_SECRET_KEY"))
    encryption_key: str = Field(
        default="dev-encryption-key-change-me", validation_alias=_env("LESSPAPER_NGL_ENCRYPTION_KEY", "FOLIUM_ENCRYPTION_KEY")
    )
    env: str = Field(default="development", validation_alias=_env("LESSPAPER_NGL_ENV", "FOLIUM_ENV"))
    log_level: str = Field(default="INFO", validation_alias=_env("LESSPAPER_NGL_LOG_LEVEL", "FOLIUM_LOG_LEVEL"))
    host: str = Field(default="0.0.0.0", validation_alias=_env("LESSPAPER_NGL_HOST", "FOLIUM_HOST"))
    port: int = Field(default=8000, validation_alias=_env("LESSPAPER_NGL_PORT", "FOLIUM_PORT"))

    admin_username: str = Field(default="admin", validation_alias=_env("LESSPAPER_NGL_ADMIN_USERNAME", "FOLIUM_ADMIN_USERNAME"))
    admin_password: str = Field(default="changeme", validation_alias=_env("LESSPAPER_NGL_ADMIN_PASSWORD", "FOLIUM_ADMIN_PASSWORD"))
    allow_registration: bool = Field(default=True, alias="ALLOW_REGISTRATION")
    default_storage_quota_bytes: int | None = Field(
        default=None, alias="DEFAULT_STORAGE_QUOTA_BYTES"
    )
    default_ai_monthly_request_quota: int | None = Field(
        default=None, alias="DEFAULT_AI_MONTHLY_REQUEST_QUOTA"
    )

    database_url: str = Field(
        default="postgresql+asyncpg://folium:folium@localhost:5433/folium",
        alias="DATABASE_URL",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://folium:folium@localhost:5433/folium",
        alias="DATABASE_URL_SYNC",
    )

    documents_path: Path = Field(default=Path("/documents"), alias="DOCUMENTS_PATH")
    consume_path: Path = Field(default=Path("/consume"), alias="CONSUME_PATH")
    export_path: Path = Field(default=Path("/export"), alias="EXPORT_PATH")
    backups_path: Path = Field(default=Path("/backups"), alias="BACKUPS_PATH")
    documents_host_source: str | None = Field(default=None, validation_alias=_env("LESSPAPER_NGL_DOCUMENTS_HOST_SOURCE", "FOLIUM_DOCUMENTS_HOST_SOURCE"))

    max_upload_size_mb: int = Field(default=100, alias="MAX_UPLOAD_SIZE_MB")
    allowed_mime_types: str = Field(
        default=(
            "application/pdf,image/png,image/jpeg,text/plain,text/markdown,"
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        alias="ALLOWED_MIME_TYPES",
    )

    # Legacy Tesseract-style codes (eng, chi_sim, …); mapped to PaddleOCR lang.
    ocr_language: str = Field(default="eng", alias="OCR_LANGUAGE")
    ocr_enabled: bool = Field(default=True, alias="OCR_ENABLED")
    # PDF page render DPI for OCR (lower = less RAM; 150 is the memory-safe default).
    ocr_dpi: int = Field(default=150, alias="OCR_DPI", ge=72, le=400)
    # When true, load Paddle in the worker process (tests/debug). Production uses a
    # short-lived subprocess so model RAM is reclaimed after each OCR job.
    ocr_in_process: bool = Field(default=False, alias="OCR_IN_PROCESS")
    # Soft timeout for one OCR subprocess (large multi-page PDFs).
    ocr_subprocess_timeout_seconds: float = Field(
        default=3600.0, alias="OCR_SUBPROCESS_TIMEOUT_SECONDS", ge=60.0
    )

    # Default 1 so OCR/indexing peaks do not stack in one worker process.
    job_concurrency: int = Field(default=1, alias="JOB_CONCURRENCY", ge=1)
    consume_poll_interval_seconds: float = Field(default=5.0, alias="CONSUME_POLL_INTERVAL_SECONDS")
    job_poll_interval_seconds: float = Field(default=2.0, alias="JOB_POLL_INTERVAL_SECONDS")
    # RUNNING jobs without a lock heartbeat older than this are re-queued.
    job_stale_running_seconds: int = Field(default=600, alias="JOB_STALE_RUNNING_SECONDS")
    job_lock_heartbeat_seconds: float = Field(default=60.0, alias="JOB_LOCK_HEARTBEAT_SECONDS")
    trash_retention_days: int = Field(default=30, alias="TRASH_RETENTION_DAYS")
    trash_purge_interval_seconds: float = Field(
        default=3600.0, alias="TRASH_PURGE_INTERVAL_SECONDS"
    )

    ai_privacy_mode: PrivacyMode = Field(default=PrivacyMode.LOCAL_ONLY, alias="AI_PRIVACY_MODE")
    ai_profile: AIProfile = Field(default=AIProfile.LIGHTWEIGHT, alias="AI_PROFILE")
    ai_allow_remote_embeddings: bool = Field(default=False, alias="AI_ALLOW_REMOTE_EMBEDDINGS")
    ai_allow_remote_qa: bool = Field(default=False, alias="AI_ALLOW_REMOTE_QA")
    ai_allow_remote_vision: bool = Field(default=False, alias="AI_ALLOW_REMOTE_VISION")
    ai_warn_before_remote: bool = Field(default=True, alias="AI_WARN_BEFORE_REMOTE")

    # Cookie names kept for session continuity across the rebrand.
    session_cookie_name: str = Field(default="folium_session", alias="SESSION_COOKIE_NAME")
    session_ttl_hours: int = Field(default=168, alias="SESSION_TTL_HOURS")
    csrf_cookie_name: str = Field(default="folium_csrf", alias="CSRF_COOKIE_NAME")
    frontend_origin: str = Field(default="http://localhost:9398", alias="FRONTEND_ORIGIN")
    secure_cookies: bool = Field(default=False, validation_alias=_env("LESSPAPER_NGL_SECURE_COOKIES", "FOLIUM_SECURE_COOKIES"))
    password_reset_token_ttl_hours: int = Field(default=1, alias="PASSWORD_RESET_TOKEN_TTL_HOURS")
    max_avatar_size_mb: int = Field(default=2, alias="MAX_AVATAR_SIZE_MB")
    consume_owner_username: str | None = Field(default=None, alias="CONSUME_OWNER_USERNAME")
    application_log_retention_days: int = Field(
        default=30, alias="APPLICATION_LOG_RETENTION_DAYS", ge=1, le=365
    )
    build_revision: str | None = Field(default=None, validation_alias=_env("LESSPAPER_NGL_BUILD_REVISION", "FOLIUM_BUILD_REVISION"))
    build_date: str | None = Field(default=None, validation_alias=_env("LESSPAPER_NGL_BUILD_DATE", "FOLIUM_BUILD_DATE"))
    repository_url: str | None = Field(default=None, validation_alias=_env("LESSPAPER_NGL_REPOSITORY_URL", "FOLIUM_REPOSITORY_URL"))
    issues_url: str | None = Field(default=None, validation_alias=_env("LESSPAPER_NGL_ISSUES_URL", "FOLIUM_ISSUES_URL"))
    docs_url: str | None = Field(default=None, validation_alias=_env("LESSPAPER_NGL_DOCS_URL", "FOLIUM_DOCS_URL"))
    releases_url: str | None = Field(default=None, validation_alias=_env("LESSPAPER_NGL_RELEASES_URL", "FOLIUM_RELEASES_URL"))
    license_url: str | None = Field(default=None, validation_alias=_env("LESSPAPER_NGL_LICENSE_URL", "FOLIUM_LICENSE_URL"))

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_avatar_bytes(self) -> int:
        return self.max_avatar_size_mb * 1024 * 1024

    @property
    def allowed_mimes(self) -> set[str]:
        return {m.strip() for m in self.allowed_mime_types.split(",") if m.strip()}

    @property
    def is_dev(self) -> bool:
        return self.env.lower() in {"development", "dev", "test"}

    @property
    def frontend_origins(self) -> list[str]:
        """Browser origins allowed for CORS and MCP (comma-separated in FRONTEND_ORIGIN)."""
        seen: set[str] = set()
        origins: list[str] = []
        for raw in self.frontend_origin.split(","):
            origin = raw.strip().rstrip("/")
            if not origin or origin in seen:
                continue
            seen.add(origin)
            origins.append(origin)
        return origins or ["http://localhost:9398"]

    @property
    def primary_frontend_origin(self) -> str:
        return self.frontend_origins[0]

    @property
    def use_secure_cookies(self) -> bool:
        if self.is_dev:
            return False
        if self.secure_cookies:
            return True
        return any(origin.startswith("https://") for origin in self.frontend_origins)

    @property
    def originals_path(self) -> Path:
        return self.documents_path / "originals"

    @property
    def previews_path(self) -> Path:
        return self.documents_path / "previews"

    @property
    def thumbnails_path(self) -> Path:
        return self.documents_path / "thumbnails"

    @property
    def avatars_path(self) -> Path:
        return self.documents_path / "avatars"

    @field_validator("ai_privacy_mode", mode="before")
    @classmethod
    def _normalize_privacy(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower().replace("-", "_").replace(" ", "_")
        return value

    @field_validator("ai_profile", mode="before")
    @classmethod
    def _normalize_profile(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
