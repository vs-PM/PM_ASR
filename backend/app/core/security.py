from datetime import datetime, timedelta, timezone
import jwt
from passlib.hash import bcrypt
from typing import Any, Optional
from app.core.config import settings

def hash_password(plain: str) -> str:
    return bcrypt.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.verify(plain, hashed)

def _encode(payload: dict, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    to_encode = {**payload, "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp())}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algo)

def create_access_token(user_id: int, role: str) -> str:
    return _encode({"sub": str(user_id), "role": role, "typ": "access"},
                   timedelta(minutes=settings.access_ttl_minutes))

def create_refresh_token(user_id: int, role: str) -> str:
    return _encode({"sub": str(user_id), "role": role, "typ": "refresh"},
                   timedelta(days=settings.refresh_ttl_days))

def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algo])
