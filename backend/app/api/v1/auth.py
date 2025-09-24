from __future__ import annotations
from fastapi import APIRouter, Depends, Response, status, Request
from pydantic import BaseModel
from sqlalchemy import select
from datetime import timedelta, datetime, timezone
from app.core.config import settings
from app.core.security import verify_password, create_access_token, _encode
from app.core.auth import require_user, require_admin
from app.core.refresh_store import save_refresh, rotate_refresh, revoke_refresh
from app.db.session import async_session
from app.db.models import MfgUser, UserRole
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

def _set_cookie(resp: Response, name: str, value: str, max_age: int, *, path: str = "/"):
    resp.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        httponly=True,
        samesite="lax" if name == "access_token" else "strict",
        secure=getattr(settings, "cookie_secure", True),
        domain=(getattr(settings, "cookie_domain", None) or None),
        path=path,
    )

def _clear_cookie(resp: Response, name: str, *, path: str = "/"):
    resp.delete_cookie(
        key=name,
        domain=(getattr(settings, "cookie_domain", None) or None),
        path=path,
    )

@router.post("/auth/login")
async def login(data: LoginIn, req: Request, resp: Response):
    async with async_session() as s:
        user = (await s.execute(select(MfgUser).where(MfgUser.login == data.username, MfgUser.is_active == True))).scalar_one_or_none()  # noqa: E712
        if not user or not verify_password(data.password, user.password_hash):
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)

        access = create_access_token(user.id, user.role.value)
        # Issue refresh (opaque + hashed in DB)
        rt = await save_refresh(s, user_id=user.id, user_agent=req.headers.get("user-agent"), ip=req.client.host)

    _set_cookie(resp, "access_token", access, getattr(settings, "access_ttl_minutes", 15) * 60, path="/")
    _set_cookie(resp, "refresh_token", rt.plain, getattr(settings, "refresh_ttl_days", 14) * 86400, path="/api/v1/auth")
    await audit_log(user.id, "login", "user", user.id)
    return {"ok": True}

@router.post("/auth/refresh")
async def refresh(req: Request, resp: Response):
    # refresh из куки (opaque)
    rt_plain = req.cookies.get("refresh_token")
    if not rt_plain:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        async with async_session() as s:
            new_rt, user = await rotate_refresh(s, rt_plain, ua=req.headers.get("user-agent"), ip=req.client.host)
            access = create_access_token(user.id, user.role.value)
    except Exception:
        # on any error -> clear cookies; client must login again
        _clear_cookie(resp, "access_token", path="/")
        _clear_cookie(resp, "refresh_token", path="/api/v1/auth")
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    _set_cookie(resp, "access_token", access, getattr(settings, "access_ttl_minutes", 15) * 60, path="/")
    _set_cookie(resp, "refresh_token", new_rt.plain, getattr(settings, "refresh_ttl_days", 14) * 86400, path="/api/v1/auth")
    return {"ok": True}

@router.post("/auth/logout")
async def logout(req: Request, resp: Response):
    rt_plain = req.cookies.get("refresh_token")
    if rt_plain:
        async with async_session() as s:
            try:
                await revoke_refresh(s, rt_plain)
            except Exception:
                pass
    _clear_cookie(resp, "access_token", path="/")
    _clear_cookie(resp, "refresh_token", path="/api/v1/auth")
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
