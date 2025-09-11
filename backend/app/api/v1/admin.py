from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, func
from app.core.auth import require_admin
from app.db.session import async_session
from app.db.models import MfgAuditLog

router = APIRouter()

@router.get("/admin/audit")
async def admin_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    object_type: Optional[str] = None,
    _=Depends(require_admin),
):
    async with async_session() as s:
        conds = []
        if user_id:     conds.append(MfgAuditLog.user_id == user_id)
        if action:      conds.append(MfgAuditLog.action == action)
        if object_type: conds.append(MfgAuditLog.object_type == object_type)

        base = select(MfgAuditLog).order_by(MfgAuditLog.created_at.desc())
        if conds: base = base.where(and_(*conds))

        total = (await s.execute(
            select(func.count(MfgAuditLog.id)).where(and_(*conds)) if conds else select(func.count(MfgAuditLog.id))
        )).scalar_one()

        rows = (await s.execute(base.offset((page-1)*page_size).limit(page_size))).scalars().all()
        items = [{
            "id": r.id, "user_id": r.user_id, "action": r.action,
            "object_type": r.object_type, "object_id": r.object_id,
            "meta": r.meta, "created_at": r.created_at
        } for r in rows]
        return {"items": items, "page": page, "page_size": page_size, "total": total}
