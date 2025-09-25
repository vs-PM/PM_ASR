from __future__ import annotations
import secrets, hashlib
from datetime import datetime, timedelta, timezone
from typing import Tuple
from sqlalchemy import select, update, insert, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import RefreshToken, MfgUser
from app.core.security import hash_password, verify_password

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _fingerprint(plain: str) -> str:
    # SHA-256 hex digest for fast lookup; store alongside argon2 hash
    return hashlib.sha256(plain.encode('utf-8')).hexdigest()

class RefreshPlain:
    def __init__(self, plain: str):
        self.plain = plain
        self.fingerprint = _fingerprint(plain)

async def save_refresh(db: AsyncSession, user_id: int, *, user_agent: str | None, ip: str | None, days: int = 14) -> RefreshPlain:
    plain = secrets.token_urlsafe(48)
    fp = _fingerprint(plain)
    hashed = hash_password(plain)
    exp = _now() + timedelta(days=days)
    await db.execute(
        insert(RefreshToken).values(
            user_id=user_id,
            token_hash=hashed,
            fingerprint=fp,
            user_agent=user_agent,
            ip=ip,
            parent_id=None,
            expires_at=exp,
            revoked_at=None,
        )
    )
    await db.commit()
    return RefreshPlain(plain)

async def _find_token_row(db: AsyncSession, plain: str):
    fp = _fingerprint(plain)
    row = (await db.execute(select(RefreshToken).where(RefreshToken.fingerprint == fp))).scalar_one_or_none()
    return row

async def rotate_refresh(db: AsyncSession, plain: str, *, ua: str | None, ip: str | None) -> Tuple[RefreshPlain, MfgUser]:
    row = await _find_token_row(db, plain)
    if not row:
        raise ValueError("refresh_not_found")

    # Verify argon2 hash
    if not verify_password(plain, row.token_hash):
        raise ValueError("refresh_mismatch")

    # Check expiry / revocation
    if row.revoked_at is not None:
        # token reuse -> revoke all user tokens
        await db.execute(update(RefreshToken).where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
                         .values(revoked_at=_now()))
        await db.commit()
        raise ValueError("refresh_reused")
    if row.expires_at <= _now():
        raise ValueError("refresh_expired")

    # Rotate: revoke current and issue a new one chained by parent_id
    await db.execute(update(RefreshToken).where(RefreshToken.id == row.id).values(revoked_at=_now()))
    new_plain = await save_refresh(db, row.user_id, user_agent=ua, ip=ip)
    # Set parent_id for the new token
    await db.execute(update(RefreshToken).where(RefreshToken.fingerprint == new_plain.fingerprint).values(parent_id=row.id))
    await db.commit()

    user = (await db.execute(select(MfgUser).where(MfgUser.id == row.user_id))).scalar_one()
    return new_plain, user

async def revoke_refresh(db: AsyncSession, plain: str) -> None:
    row = await _find_token_row(db, plain)
    if row and row.revoked_at is None:
        await db.execute(update(RefreshToken).where(RefreshToken.id == row.id).values(revoked_at=_now()))
        await db.commit()
