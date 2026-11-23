"""Management commands: python -m app.cli create-admin <phone> | announce-due"""

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


async def announce_due(session: AsyncSession) -> int:
    """Announce approved promotions that have started but were not announced yet.

    Run periodically (e.g. cron every 10 minutes). Returns how many were announced.
    """
    from app.modules.notifications.push import get_push_sender, send_all
    from app.modules.notifications.service import notify_promotion_published, push_messages
    from app.modules.promotions.models import Promotion, active_clause
    from app.timeutil import utcnow

    due = list(
        await session.scalars(
            select(Promotion).where(active_clause(utcnow()), Promotion.announced_at.is_(None))
        )
    )
    announced = 0
    for promo in due:
        notifications = await notify_promotion_published(session, promo)
        if promo.announced_at is None:
            # Shop hidden right now: mark it so the job does not retry every run.
            promo.announced_at = utcnow()
            await session.commit()
            continue
        announced += 1
        await send_all(await push_messages(session, notifications), get_push_sender())
    return announced


async def _main(args: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        if args.command == "create-admin":
            user = await create_admin(session, args.phone)
            print(f"admin: id={user.id} phone={user.phone}")
        elif args.command == "announce-due":
            print(f"announced: {await announce_due(session)}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="create or promote a user to admin")
    admin.add_argument("phone")
    sub.add_parser("announce-due", help="notify followers about promotions that have started")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
