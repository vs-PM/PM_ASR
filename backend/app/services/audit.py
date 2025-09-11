from __future__ import annotations
from typing import Optional, Any
from sqlalchemy import insert
from app.db.session import async_session
from app.db.models import MfgAuditLog

async def audit_log(
    user_id: Optional[int],
    action: str,
    object_type: Optional[str] = None,
    object_id: Optional[int] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    async with async_session() as s:
        await s.execute(insert(MfgAuditLog).values(
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            meta=meta or {},
        ))
        await s.commit()
