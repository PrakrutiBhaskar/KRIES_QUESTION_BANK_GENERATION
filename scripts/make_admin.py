#!/usr/bin/env python3
"""
Give an existing account the Admin role (or take it away).

Administrators manage the shared figure library in the web app: they upload
diagrams, tag them with a subject / chapter and list the labelled parts, and
every teacher can then write diagram-based questions from them and print the
diagrams in the answer key.

The role is deliberately not self-service. Sign-up only offers Teacher and
Student, and PATCH /auth/me refuses to set Admin, so the only way to become an
administrator is for someone with access to the server to run this script.

The person must already have an account (sign up in the app first). They need to
sign out and back in, or reload, for the new role to show.

Examples:
    python scripts/make_admin.py principal@school.in
    python scripts/make_admin.py principal@school.in --demote     # back to Teacher
    python scripts/make_admin.py --list
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.db import build_engine  # noqa: E402
from app.models import User  # noqa: E402
from app.services import auth as auth_service  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Grant or revoke the Admin role.")
    ap.add_argument("email", nargs="?", help="Email of an existing account")
    ap.add_argument("--demote", action="store_true", help="Make the account a Teacher again")
    ap.add_argument("--list", action="store_true", help="List the current administrators")
    args = ap.parse_args(argv)
    if not args.list and not args.email:
        ap.error("give an email address, or use --list")
    return args


async def run(args: argparse.Namespace) -> int:
    engine = build_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            if args.list:
                admins = (
                    await session.scalars(select(User).where(User.role == "Admin").order_by(User.email))
                ).all()
                if not admins:
                    print("No administrators yet.")
                for u in admins:
                    print(f"{u.email}  ({u.name})")
                return 0

            email = args.email.strip().lower()
            user = await auth_service.get_by_email(session, email)
            if user is None:
                print(f"No account with email {email!r}. Ask them to sign up in the app first.")
                return 2
            target = "Teacher" if args.demote else "Admin"
            if user.role == target:
                print(f"{user.email} is already {target}.")
                return 0
            if args.demote and user.role != "Admin":
                print(f"{user.email} is a {user.role}, not an administrator.")
                return 1
            user.role = target
            await session.commit()
            print(f"{user.email} is now {target}.")
            return 0
    finally:
        await engine.dispose()


def main() -> None:
    sys.exit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
