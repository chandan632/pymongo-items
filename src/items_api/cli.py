from __future__ import annotations

import argparse
import asyncio
import sys


async def _create_admin(email: str, password: str) -> None:
    from items_api.db import close_db, connect_db, get_database
    from items_api.repositories.user_repository import UserRepository
    from items_api.services.auth_service import create_admin_user

    await connect_db()
    try:
        user_repo = UserRepository(get_database()["users"])
        await user_repo.ensure_indexes()
        user = await create_admin_user(user_repo, email, password)
        print(f"Created admin user: {user['email']} ({user['id']})")
    finally:
        await close_db()


def create_admin_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("email", help="Admin email address")
    parser.add_argument("password", help="Admin password (min 8 characters)")
    args = parser.parse_args(argv)
    try:
        asyncio.run(_create_admin(args.email, args.password))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Items API CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin = subparsers.add_parser("create-admin", help="Create an admin user")
    create_admin.add_argument("email", help="Admin email address")
    create_admin.add_argument("password", help="Admin password (min 8 characters)")

    args = parser.parse_args(argv)

    if args.command == "create-admin":
        create_admin_main([args.email, args.password])


if __name__ == "__main__":
    main()
