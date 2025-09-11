from fastapi import Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session
from app.db.models import MfgUser, UserRole
from app.core.security import decode_token

async def get_current_user(req: Request) -> MfgUser:
    token = req.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(token)
        if payload.get("typ") != "access":
            raise ValueError("wrong typ")
        uid = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    async with async_session() as s:
        user = (await s.execute(select(MfgUser).where(MfgUser.id == uid, MfgUser.is_active == True))).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

def require_user(user: MfgUser = Depends(get_current_user)) -> MfgUser:
    return user

def require_admin(user: MfgUser = Depends(get_current_user)) -> MfgUser:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user
