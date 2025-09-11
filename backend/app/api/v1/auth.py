from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from app.core.config import settings
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token, _encode
from app.core.auth import require_user, require_admin
from app.db.session import async_session
from app.db.models import MfgUser, UserRole
from datetime import timedelta, datetime, timezone
from app.services.audit import audit_log

router = APIRouter()

class LoginIn(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    login: str
    role: UserRole
    class Config: from_attributes = True

def _set_cookie(resp: Response, name: str, value: str, max_age: int):
    resp.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        domain=settings.cookie_domain or None,
        path="/",
    )

def _clear_cookie(resp: Response, name: str):
    resp.delete_cookie(
        key=name,
        domain=settings.cookie_domain or None,
        path="/",
    )

@router.post("/auth/login")
async def login(data: LoginIn, resp: Response):
    async with async_session() as s:
        user = (await s.execute(select(MfgUser).where(MfgUser.login == data.username, MfgUser.is_active == True))).scalar_one_or_none()
        if not user or not verify_password(data.password, user.password_hash):
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
    access = create_access_token(user.id, user.role.value)
    refresh = create_refresh_token(user.id, user.role.value)
    _set_cookie(resp, "access_token", access, settings.access_ttl_minutes * 60)
    _set_cookie(resp, "refresh_token", refresh, settings.refresh_ttl_days * 86400)
    await audit_log(user.id, "login", "user", user.id)
    return {"user": UserOut.model_validate(user).model_dump()}

@router.post("/auth/refresh")
async def refresh(resp: Response):
    # refresh из куки
    try:
        payload = decode_token(resp.request.cookies.get("refresh_token"))
        if payload.get("typ") != "refresh":
            raise ValueError("wrong typ")
        uid = int(payload["sub"]); role = payload["role"]
        await audit_log(None, "refresh")
    except Exception:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    access = create_access_token(uid, role)
    _set_cookie(resp, "access_token", access, settings.access_ttl_minutes * 60)
    return {"ok": True}

@router.post("/auth/logout")
async def logout(resp: Response):
    _clear_cookie(resp, "access_token")
    _clear_cookie(resp, "refresh_token")
    await audit_log(None, "logout")
    return {"ok": True}

@router.get("/auth/me")
async def me(user: MfgUser = Depends(require_user)):
    return {"user": {"id": user.id, "login": user.login, "role": user.role}}

# короткоживущий токен для WebSocket, если хочешь использовать ?token=...
@router.get("/auth/ws-token")
async def ws_token(user: MfgUser = Depends(require_user)):
    # 60 секунд TTL
    now = datetime.now(timezone.utc)
    return {
        "token": _encode({"sub": str(user.id), "role": user.role.value, "typ": "ws"}, timedelta(seconds=60))
    }
