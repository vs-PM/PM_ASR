from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from passlib.context import CryptContext
from app.core.config import settings

# Use Argon2id for password & token hashing
_pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)

def _encode(payload: dict, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    to_encode = {**payload, "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp())}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algo)

def create_access_token(user_id: int, role: str) -> str:
    return _encode({"sub": str(user_id), "role": role, "typ": "access"},
                   timedelta(minutes=getattr(settings, 'access_ttl_minutes', 15)))

def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algo])
