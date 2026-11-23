from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.users.models import OtpCode, RefreshToken, User
from app.modules.users.schemas import TokenPair
from app.modules.users.sms import SmsSender
from app.security import (
    create_access_token,
    generate_otp,
    generate_refresh_token,
    hash_otp,
    hash_token,
)
from app.timeutil import utcnow

OTP_PER_MINUTE = 1
OTP_PER_HOUR = 5
OTP_PER_DAY = 10


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


async def _otp_count_since(session: AsyncSession, phone: str, since) -> int:
    stmt = select(func.count()).where(OtpCode.phone == phone, OtpCode.created_at > since)
    return await session.scalar(stmt) or 0


async def request_otp(session: AsyncSession, phone: str, sms: SmsSender) -> None:
    now = utcnow()
    if (
        await _otp_count_since(session, phone, now - timedelta(minutes=1)) >= OTP_PER_MINUTE
        or await _otp_count_since(session, phone, now - timedelta(hours=1)) >= OTP_PER_HOUR
        or await _otp_count_since(session, phone, now - timedelta(days=1)) >= OTP_PER_DAY
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "otp_rate_limited")
    code = generate_otp()
    session.add(
        OtpCode(
            phone=phone,
            code_hash=hash_otp(phone, code),
            created_at=now,
            expires_at=now + timedelta(minutes=get_settings().otp_ttl_minutes),
        )
    )
    await session.commit()
    await sms.send(phone, f"Nirede: {code}")


async def verify_otp(session: AsyncSession, phone: str, code: str) -> User:
    otp = await session.scalar(
        select(OtpCode).where(OtpCode.phone == phone).order_by(OtpCode.id.desc()).limit(1)
    )
    if otp is None:
        raise _unauthorized("otp_invalid")
    if otp.expires_at <= utcnow():
        raise _unauthorized("otp_expired")
    # Reserve an attempt atomically before comparing; a NULL result means the limit is used up.
    attempts = await session.scalar(
        update(OtpCode)
        .where(OtpCode.id == otp.id, OtpCode.attempts < get_settings().otp_max_attempts)
        .values(attempts=OtpCode.attempts + 1)
        .returning(OtpCode.attempts)
    )
    if attempts is None:
        await session.commit()
        raise _unauthorized("otp_expired")
    if otp.code_hash != hash_otp(phone, code):
        await session.commit()
        raise _unauthorized("otp_invalid")

    await session.execute(delete(OtpCode).where(OtpCode.phone == phone))
    user = await session.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone)
        session.add(user)
    await session.commit()
    return user


async def issue_tokens(session: AsyncSession, user: User) -> TokenPair:
    raw = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(days=get_settings().refresh_ttl_days),
        )
    )
    await session.commit()
    return TokenPair(access_token=create_access_token(user.id, user.role), refresh_token=raw)


async def _revoke_live_refresh(session: AsyncSession, raw: str) -> int:
    """Atomically revoke a live refresh token and return its user id; 401 if not live."""
    now = utcnow()
    user_id = await session.scalar(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_token(raw),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(RefreshToken.user_id)
    )
    if user_id is None:
        raise _unauthorized("invalid_refresh_token")
    return user_id


async def rotate_refresh(session: AsyncSession, raw: str) -> TokenPair:
    user = await session.get(User, await _revoke_live_refresh(session, raw))
    if user is None:
        raise _unauthorized("invalid_refresh_token")
    return await issue_tokens(session, user)


async def revoke_refresh(session: AsyncSession, raw: str) -> None:
    await _revoke_live_refresh(session, raw)
    await session.commit()


async def update_me(session: AsyncSession, user: User, data) -> User:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    return user
