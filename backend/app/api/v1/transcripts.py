from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.core.logger import get_logger
from app.core.auth import require_user
from app.db.session import async_session
from app.db.models import MfgTranscript, MfgJob, MfgFile
from app.schemas.api import TranscriptCreateIn, TranscriptCreateOut

log = get_logger(__name__)
router = APIRouter()


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
async def _kickoff_transcription(transcript_id: int, audio_path: str) -> None:
    """Fire-and-forget запуск пайплайна транскрипции.
    
    Пытаемся импортировать функцию process_transcription. Если это корутина — ждём,
    если синхронная — выполняем в текущем loop через to_thread.
    """
    try:
        from app.services.jobs.api import process_transcription  # type: ignore
    except Exception:
        log.exception("Не удалось импортировать process_transcription")
        return

    try:
        result = process_transcription(transcript_id, audio_path)  # type: ignore
        if inspect.iscoroutine(result):
            await result  # type: ignore[func-returns-value]
        # если синхронная — просто выполнится
    except Exception:
        log.exception("Ошибка фонового запуска транскрипции", extra={"transcript_id": transcript_id})


def _serialize_item(tr: MfgTranscript, job: Optional[MfgJob]) -> Dict[str, Any]:
    return {
        "id": tr.id,
        "meeting_id": getattr(tr, "meeting_id", None),
        "title": getattr(tr, "title", None),
        "status": getattr(tr, "status", None),
        "filename": getattr(tr, "filename", None),
        "file_id": getattr(tr, "file_id", None),
        "created_at": getattr(tr, "created_at", None),
        "updated_at": getattr(tr, "updated_at", None),
        "job": None
        if job is None
        else {
            "status": getattr(job, "status", None),
            "progress": getattr(job, "progress", None),
            "step": getattr(job, "step", None),
            "error": getattr(job, "error", None),
            "started_at": getattr(job, "started_at", None),
            "finished_at": getattr(job, "finished_at", None),
        },
    }


# ----------------------------------------------------------------------------
# List transcripts (only current user's)
# ----------------------------------------------------------------------------
@router.get("/")
async def list_transcripts(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(require_user),
):
    """Список транскриптов текущего пользователя с кратким статусом job.
    Возвращает { items, total }.
    """
    async with async_session() as s:
        total_q = select(func.count(MfgTranscript.id)).where(MfgTranscript.user_id == user.id)
        total = (await s.execute(total_q)).scalar_one()

        q = (
            select(MfgTranscript, MfgJob)
            .join(MfgJob, MfgJob.transcript_id == MfgTranscript.id, isouter=True)
            .where(MfgTranscript.user_id == user.id)
            .order_by(MfgTranscript.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows: List[Tuple[MfgTranscript, Optional[MfgJob]]] = (await s.execute(q)).all()  # type: ignore

        items = [_serialize_item(tr, job) for tr, job in rows]
        return {"items": items, "total": total}


# ----------------------------------------------------------------------------
# Get one transcript by id (user-scoped)
# ----------------------------------------------------------------------------
@router.get("/{transcript_id}")
async def get_transcript(transcript_id: int, user=Depends(require_user)):
    async with async_session() as s:
        q = (
            select(MfgTranscript, MfgJob)
            .join(MfgJob, MfgJob.transcript_id == MfgTranscript.id, isouter=True)
            .where(MfgTranscript.id == transcript_id, MfgTranscript.user_id == user.id)
        )
        row = (await s.execute(q)).first()
        if not row:
            raise HTTPException(status_code=404, detail="Transcript not found")
        tr, job = row
        return _serialize_item(tr, job)


# ----------------------------------------------------------------------------
# Create transcript by file_id (JSON body)
# ----------------------------------------------------------------------------
@router.post("/", response_model=TranscriptCreateOut, status_code=201)
async def create_transcript(data: TranscriptCreateIn, user=Depends(require_user)):
    """Создать транскрипт, указывая уже загруженный файл (file_id).
    
    Для обратной совместимости сохраняем и file_id, и file_path (путь на диск).
    После создания — асинхронно запускаем пайплайн.
    """
    async with async_session() as s:
        # Проверим наличие файла и принадлежность пользователю
        f = (
            await s.execute(
                select(MfgFile).where(MfgFile.id == data.file_id, MfgFile.user_id == user.id)
            )
        ).scalar_one_or_none()
        if not f:
            raise HTTPException(status_code=404, detail="File not found")

        tr = MfgTranscript(
            meeting_id=data.meeting_id,
            title=data.title,
            status="processing",
            file_id=f.id,
            file_path=f.stored_path,  # 🔴 legacy совместимость для существующих шагов
            filename=f.filename,
            user_id=user.id,
        )
        s.add(tr)
        await s.commit()
        await s.refresh(tr)

        # Пнули пайплайн (не блокируем ответ)
        asyncio.create_task(_kickoff_transcription(tr.id, f.stored_path))

        return TranscriptCreateOut(transcript_id=tr.id, status="processing")


# ----------------------------------------------------------------------------
# (Optional) Update title
# ----------------------------------------------------------------------------
@router.patch("/{transcript_id}")
async def rename_transcript(transcript_id: int, title: str, user=Depends(require_user)):
    """Переименовать транскрипт (удобно для UI)."""
    async with async_session() as s:
        tr = (
            await s.execute(
                select(MfgTranscript).where(MfgTranscript.id == transcript_id, MfgTranscript.user_id == user.id)
            )
        ).scalar_one_or_none()
        if not tr:
            raise HTTPException(status_code=404, detail="Transcript not found")
        tr.title = title
        await s.commit()
        await s.refresh(tr)
        return {"id": tr.id, "title": tr.title}
