# app/v1/meetings.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.api import MeetingCreateIn, MeetingCreateOut, MeetingGetOut
from app.core.auth import require_user  # если гостям можно — уберите зависимость
from app.db.session import get_session
from app.db.models import MfgTranscript, MfgFile
from app.services.audit import audit_log

router = APIRouter()


@router.post("/", response_model=MeetingCreateOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    body: MeetingCreateIn,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),  # уберите, если не нужна аутентификация
):
    # 1) Валидируем наличие файла
    f = (await session.execute(
        select(MfgFile).where(MfgFile.id == body.file_id)
    )).scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=422, detail="file_id not found")

    # 2) Создаём transcript БЕЗ запуска пайплайна
    t = MfgTranscript(
        meeting_id=body.meeting_id,
        file_id=body.file_id,
        filename=getattr(f, "filename", None),
        title=body.title or None,
        status="queued",
        user_id=getattr(user, "id", None) if user else None,
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)

    # 3) Аудит (по желанию)
    try:
        await audit_log(getattr(user, "id", None), "create", "transcript", t.id, {
            "file_id": body.file_id,
            "meeting_id": body.meeting_id,
            "title": body.title or None,
        })
    except Exception:
        # аудит не должен рушить основной поток
        pass

    return MeetingCreateOut(id=t.id, status=t.status)


@router.get("/{transcript_id}", response_model=MeetingGetOut)
async def get_meeting(
    transcript_id: int,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
):
    t = (await session.execute(
        select(MfgTranscript).where(MfgTranscript.id == transcript_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return MeetingGetOut(
        id=t.id,
        meeting_id=t.meeting_id,
        file_id=t.file_id,
        filename=getattr(t, "filename", None),
        title=t.title,
        status=t.status,
        error=getattr(t, "error", None),
        created_at=getattr(t, "created_at", None).isoformat() if getattr(t, "created_at", None) else None,
        updated_at=getattr(t, "updated_at", None).isoformat() if getattr(t, "updated_at", None) else None,
        text=getattr(t, "text", None),
    )
