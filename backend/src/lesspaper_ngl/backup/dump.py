"""PostgreSQL dump/restore helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from lesspaper_ngl.core.config import Settings, get_settings

_DSN_SECRET_RE = re.compile(r"(password=)[^\s]+", re.IGNORECASE)
_PG_BIN_DIRS = (Path("/usr/lib/postgresql/17/bin"), Path("/usr/pgsql-17/bin"))
_PG17_VERSION = re.compile(r"\s17[\s.]")


def _pg_bin(name: str) -> str:
    for directory in _PG_BIN_DIRS:
        candidate = directory / name
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    return found or name


def pg_tools_available() -> bool:
    binary = _pg_bin("pg_dump")
    result = subprocess.run([binary, "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        return False
    return bool(_PG17_VERSION.search(result.stdout or ""))


def _parse_sync_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").split("+", 1)[0]
    if scheme not in {"postgresql", "postgres"}:
        raise ValueError("Unsupported database URL scheme")
    dbname = (parsed.path or "").lstrip("/") or "folium"
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "folium",
        "password": parsed.password or "",
        "dbname": dbname,
    }


def _pg_env(settings: Settings | None = None) -> dict[str, str]:
    settings = settings or get_settings()
    params = _parse_sync_url(settings.database_url_sync)
    env = os.environ.copy()
    if params["password"]:
        env["PGPASSWORD"] = params["password"]
    return env


def _scrub_error(text: str) -> str:
    return _DSN_SECRET_RE.sub(r"\1***", text)


def run_pg_dump(dest: Path, *, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    params = _parse_sync_url(settings.database_url_sync)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _pg_bin("pg_dump"),
        "-h",
        params["host"],
        "-p",
        params["port"],
        "-U",
        params["user"],
        "-d",
        params["dbname"],
        "-Fc",
        "--no-owner",
        "--no-acl",
        "--exclude-table-data=application_logs",
        "--exclude-table-data=sessions",
        "-f",
        str(dest),
    ]
    result = subprocess.run(cmd, env=_pg_env(settings), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(_scrub_error(result.stderr.strip() or "pg_dump failed"))


def run_pg_restore(dest_db_params: dict[str, str], dump_path: Path, *, clean: bool = True) -> None:
    env = os.environ.copy()
    if dest_db_params.get("password"):
        env["PGPASSWORD"] = dest_db_params["password"]
    cmd = [
        _pg_bin("pg_restore"),
        "-h",
        dest_db_params["host"],
        "-p",
        dest_db_params["port"],
        "-U",
        dest_db_params["user"],
        "-d",
        dest_db_params["dbname"],
        "--no-owner",
        "--no-acl",
    ]
    if clean:
        cmd.extend(["--clean", "--if-exists"])
    cmd.append(str(dump_path))
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    # pg_restore may exit 1 with warnings on --clean; treat stderr-only as ok if returncode <= 1
    if result.returncode > 1:
        raise RuntimeError(_scrub_error(result.stderr.strip() or "pg_restore failed"))


def validate_dump_readable(dump_path: Path) -> None:
    result = subprocess.run(
        [_pg_bin("pg_restore"), "--list", str(dump_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Database dump is not readable")


def terminate_other_connections(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    params = _parse_sync_url(settings.database_url_sync)
    sql = (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = current_database() AND pid <> pg_backend_pid();"
    )
    cmd = [
        _pg_bin("psql"),
        "-h",
        params["host"],
        "-p",
        params["port"],
        "-U",
        params["user"],
        "-d",
        params["dbname"],
        "-c",
        sql,
    ]
    subprocess.run(cmd, env=_pg_env(settings), capture_output=True, text=True, check=False)
