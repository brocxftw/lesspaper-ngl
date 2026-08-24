#!/usr/bin/env python3
"""Pin release compose/.env.example to an exact LESSPAPER_NGL_VERSION."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

PREFIX = "LESS" + "PAPER" + "_NGL"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=os.environ.get("VERSION", ""))
    parser.add_argument("--compose-in", default="docker-compose.yml")
    parser.add_argument("--compose-out", default="dist/docker-compose.yml")
    parser.add_argument("--env-in", default=".env.example")
    parser.add_argument("--env-out", default="dist/env.example")
    args = parser.parse_args()
    version = args.version.strip()
    if not version:
        raise SystemExit("VERSION is required")

    compose_in = Path(args.compose_in)
    compose_out = Path(args.compose_out)
    compose_out.parent.mkdir(parents=True, exist_ok=True)
    src = compose_in.read_text()
    old = "${" + PREFIX + "_VERSION:-${FOLIUM_VERSION:-latest}}"
    new = "${" + PREFIX + "_VERSION:-" + version + "}"
    if old not in src:
        raise SystemExit(f"compose pin pattern missing: {old!r}")
    compose_out.write_text(src.replace(old, new))

    env_in = Path(args.env_in)
    env_out = Path(args.env_out)
    key = PREFIX + "_VERSION="
    lines: list[str] = []
    replaced = False
    for line in env_in.read_text().splitlines(True):
        if line.startswith(key) or line.startswith("FOLIUM_VERSION="):
            if not replaced:
                lines.append(f"{key}{version}\n")
                replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.insert(0, f"{key}{version}\n")
    env_out.write_text("".join(lines))


if __name__ == "__main__":
    main()
