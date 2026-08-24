"""CLI entrypoints for lesspaper-ngl operations."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import NotFoundError, ValidationError
from lesspaper_ngl.core.logging import setup_logging
from lesspaper_ngl.db.session import dispose_engine, session_scope
from lesspaper_ngl.services import users as user_service


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folium",
        description="lesspaper-ngl operations (password recovery, maintenance)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    reset = sub.add_parser(
        "reset-admin-password",
        help=(
            "Reset an account password (locked-out recovery). "
            "Does not use LESSPAPER_NGL_ADMIN_PASSWORD from .env — that is first-boot only."
        ),
    )
    reset.add_argument(
        "--username",
        default=None,
        help="Username to reset (default: earliest active admin)",
    )
    reset.add_argument(
        "--password",
        default=None,
        help="New password (prompted if omitted)",
    )
    reset.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args(argv)
    if args.command == "reset-admin-password":
        asyncio.run(_reset_admin_password(args.username, args.password, args.yes))
    else:
        parser.error(f"Unknown command: {args.command}")


async def _reset_admin_password(
    username: str | None, password: str | None, skip_confirm: bool
) -> None:
    setup_logging()
    get_settings.cache_clear()

    if password is None:
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match", file=sys.stderr)
            sys.exit(1)

    try:
        async with session_scope() as session:
            target = await user_service.resolve_admin_user(session, username=username)
            if not skip_confirm:
                print(
                    f"Reset password for @{target.username} "
                    f"(admin={target.is_admin}, id={target.id})?"
                )
                answer = input("Type yes to continue: ").strip().lower()
                if answer not in {"y", "yes"}:
                    print("Aborted")
                    return
            await user_service.admin_set_password(session, target.id, password)
        print(f"Password updated for @{target.username}. All sessions revoked.")
    except (NotFoundError, ValidationError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    main()
