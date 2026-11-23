"""Management commands. Usage: python -m app.cli create-admin <phone>"""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.db import SessionLocal
from app.enums import UserRole
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
        user = await create_admin(session, args.phone)
        print(f"admin: id={user.id} phone={user.phone}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="create or promote a user to admin")
    admin.add_argument("phone")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
