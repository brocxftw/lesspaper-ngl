"""FRONTEND_ORIGIN parsing and secure-cookie policy."""

from __future__ import annotations

import pytest

from lesspaper_ngl.core.config import Settings


def test_frontend_origins_comma_separated() -> None:
    settings = Settings(FRONTEND_ORIGIN="https://a.example.com,http://192.168.1.1:9398")
    assert settings.frontend_origins == [
        "https://a.example.com",
        "http://192.168.1.1:9398",
    ]
    assert settings.primary_frontend_origin == "https://a.example.com"


def test_frontend_origins_dedupes() -> None:
    settings = Settings(
        FRONTEND_ORIGIN="https://a.example.com/,https://a.example.com,http://localhost:9398"
    )
    assert settings.frontend_origins == ["https://a.example.com", "http://localhost:9398"]


def test_use_secure_cookies_https_origin() -> None:
    settings = Settings(
        env="production",
        FRONTEND_ORIGIN="https://app.example.com,http://192.168.1.1:9398",
    )
    assert settings.use_secure_cookies is True


def test_use_secure_cookies_http_only() -> None:
    settings = Settings(env="production", FRONTEND_ORIGIN="http://192.168.1.1:9398")
    assert settings.use_secure_cookies is False


def test_use_secure_cookies_explicit_override() -> None:
    settings = Settings(
        env="production",
        FRONTEND_ORIGIN="http://192.168.1.1:9398",
        secure_cookies=True,
    )
    assert settings.use_secure_cookies is True


def test_use_secure_cookies_dev() -> None:
    settings = Settings(
        env="development",
        FRONTEND_ORIGIN="https://app.example.com",
        secure_cookies=True,
    )
    assert settings.use_secure_cookies is False


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    from lesspaper_ngl.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://a.test,http://b.test")
    monkeypatch.setenv("LESSPAPER_NGL_ENV", "production")
    settings = Settings()
    assert settings.frontend_origins == ["https://a.test", "http://b.test"]
    assert settings.env == "production"


def test_settings_accepts_legacy_folium_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LESSPAPER_NGL_ENV", raising=False)
    monkeypatch.setenv("FOLIUM_ENV", "production")
    settings = Settings()
    assert settings.env == "production"
