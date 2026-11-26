"""Management commands: python -m app.cli create-admin <phone> | announce-due"""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.db import SessionLocal
from app.enums import UserRole
from app.modules.notifications.push import get_push_sender
from app.modules.notifications.service import announce_due
from app.modules.users.models import User
from app.phone import normalize_phone


async def create_admin(session: AsyncSession, phone: str) -> User:
    phone = normalize_phone(phone)
    user = await session.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone)
        session.add(user)
    user.role = UserRole.admin
    await session.commit()
    return user


async def _main(args: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        if args.command == "create-admin":
            user = await create_admin(session, args.phone)
            print(f"admin: id={user.id} phone={user.phone}")
        elif args.command == "announce-due":
            print(f"announced: {await announce_due(session, get_push_sender())}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="create or promote a user to admin")
    admin.add_argument("phone")
    sub.add_parser("announce-due", help="notify followers about promotions that have started")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
