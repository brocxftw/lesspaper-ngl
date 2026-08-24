"""App version resolution."""

from __future__ import annotations

from lesspaper_ngl.core.version import get_app_version, is_prerelease_version, normalize_version


def test_normalize_version_strips_release_prefix() -> None:
    assert normalize_version("  v0.1.16  ") == "0.1.16"
    assert normalize_version("V1.2.3") == "1.2.3"
    assert normalize_version("0.1.16") == "0.1.16"
    assert normalize_version("vnext") == "vnext"
    assert normalize_version("v0.1.24-beta.1") == "0.1.24-beta.1"


def test_is_prerelease_version() -> None:
    assert is_prerelease_version("v0.1.24-beta.1") is True
    assert is_prerelease_version("0.1.24-beta") is True
    assert is_prerelease_version("0.1.23") is False
    assert is_prerelease_version("v0.1.23") is False


def test_get_app_version_prefers_env(monkeypatch) -> None:
    from lesspaper_ngl.core import version as version_mod

    get_app_version.cache_clear()
    monkeypatch.delenv("FOLIUM_VERSION", raising=False)
    monkeypatch.setenv("LESSPAPER_NGL_VERSION", "v2.3.4")
    monkeypatch.setattr(version_mod, "_git_describe", lambda _cwd: "should-not-use")
    assert get_app_version() == "2.3.4"
    get_app_version.cache_clear()


def test_get_app_version_falls_back_to_folium_env(monkeypatch) -> None:
    from lesspaper_ngl.core import version as version_mod

    get_app_version.cache_clear()
    monkeypatch.delenv("LESSPAPER_NGL_VERSION", raising=False)
    monkeypatch.setenv("FOLIUM_VERSION", "v1.2.3")
    monkeypatch.setattr(version_mod, "_git_describe", lambda _cwd: "should-not-use")
    assert get_app_version() == "1.2.3"
    get_app_version.cache_clear()
