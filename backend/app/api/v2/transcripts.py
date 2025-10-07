from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.api.v1.auth import require_user          # ← используем тот же guard, что и в v2/segment
from app.db.session import async_session, get_session
from app.db.models import (
    MfgTranscript, MfgJob, MfgFile,
    MfgSegment, MfgSpeaker, MfgDiarization
)
from app.schemas.api import TranscriptCreateIn, TranscriptCreateOut

log = get_logger(__name__)
router = APIRouter()


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
async def _kickoff_transcription(transcript_id: int, audio_path: str) -> None:
    """Fire-and-forget запуск пайплайна транскрипции.

    Пытаемся импортировать функцию process_transcription. Если это корутина — ждём,
    если синхронная — выполняем в текущем loop.
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
        # Тексты для деталей (на будущее)
        "processed_text": getattr(tr, "processed_text", None),
        "raw_text": getattr(tr, "raw_text", None),
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
# Get one transcript by id (user-scoped) + optional mode filter for segments
# ----------------------------------------------------------------------------
@router.get("/{transcript_id}")
async def get_transcript(
    transcript_id: int,
    mode: str | None = Query(None, description="Фильтр по режиму сегментов/диаризации"),
    user=Depends(require_user),
):
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
        base = _serialize_item(tr, job)

        # Сегменты (с учётом mode)
        seg_q = (
            select(MfgSegment)
            .where(MfgSegment.transcript_id == tr.id)
            .order_by(MfgSegment.start_ts.asc(), MfgSegment.end_ts.asc())
        )
        if mode:
            seg_q = seg_q.where(MfgSegment.mode == mode)
        seg_rows = (await s.execute(seg_q)).scalars().all()

        segments = [
            {
                "id": s.id,
                "start_ts": float(s.start_ts) if s.start_ts is not None else None,
                "end_ts": float(s.end_ts) if s.end_ts is not None else None,
                "text": s.text or "",
                "speaker": s.speaker,
                "lang": s.lang,
                # "mode": s.mode,  # можно вернуть, если нужно в UI
            }
            for s in seg_rows
        ]

        # Спикеры (справочник) — без режима (общие)
        spk_rows = (await s.execute(
            select(MfgSpeaker)
            .where(MfgSpeaker.transcript_id == tr.id)
            .order_by(MfgSpeaker.speaker.asc())
        )).scalars().all()
        speakers = [
            {
                "id": sp.id,
                "speaker": sp.speaker,
                "display_name": sp.display_name,
                "color": sp.color,
                "is_active": sp.is_active,
            }
            for sp in spk_rows
        ]

        # Диаризация (режимно, если надо смотреть только один набор)
        diar_q = (
            select(MfgDiarization)
            .where(MfgDiarization.transcript_id == tr.id)
            .order_by(MfgDiarization.start_ts.asc())
        )
        if mode:
            diar_q = diar_q.where(MfgDiarization.mode == mode)
        diar_rows = (await s.execute(diar_q)).scalars().all()
        diarization = [
            {
                "id": d.id,
                "start_ts": float(d.start_ts) if d.start_ts is not None else None,
                "end_ts": float(d.end_ts) if d.end_ts is not None else None,
                "speaker": d.speaker,
                # "mode": d.mode,  # по желанию
            }
            for d in diar_rows
        ]

        return {
            **base,
            "segments": segments,
            "speakers": speakers,
            "diarization": diarization,
        }


# ----------------------------------------------------------------------------
# Create transcript by file_id (JSON body)
# ----------------------------------------------------------------------------
@router.post("/", response_model=TranscriptCreateOut, status_code=201)
async def create_transcript(data: TranscriptCreateIn, user=Depends(require_user)):
    """Создать транскрипт, указывая уже загруженный файл (file_id).
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
            file_path=f.stored_path,  # legacy совместимость
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


# ----------------------------------------------------------------------------
# Get by meeting_id (latest), enriched; optional mode filter
# ----------------------------------------------------------------------------
@router.get("/by-meeting/{meeting_id}")
async def get_transcript_by_meeting(
    meeting_id: int,
    mode: str | None = Query(None, description="Фильтр по режиму сегментов/диаризации"),
    user = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Вернуть по meeting_id:
      - один (последний) транскрипт пользователя,
      - job-статус,
      - сегменты (по mode, если указан),
      - спикеров,
      - интервалы диаризации (по mode, если указан).
    """
    q = (
        select(MfgTranscript, MfgJob)
        .join(MfgJob, MfgJob.transcript_id == MfgTranscript.id, isouter=True)
        .where(MfgTranscript.user_id == user.id, MfgTranscript.meeting_id == meeting_id)
        .order_by(MfgTranscript.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(q)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Transcript not found for meeting")

    tr, job = row
    base = _serialize_item(tr, job)

    seg_q = (
        select(MfgSegment)
        .where(MfgSegment.transcript_id == tr.id)
        .order_by(MfgSegment.start_ts.asc(), MfgSegment.end_ts.asc())
    )
    if mode:
        seg_q = seg_q.where(MfgSegment.mode == mode)
    seg_rows = (await session.execute(seg_q)).scalars().all()
    segments = [
        {
            "id": s.id,
            "start_ts": float(s.start_ts) if s.start_ts is not None else None,
            "end_ts": float(s.end_ts) if s.end_ts is not None else None,
            "text": s.text or "",
            "speaker": s.speaker,
            "lang": s.lang,
        }
        for s in seg_rows
    ]

    spk_rows = (await session.execute(
        select(MfgSpeaker)
        .where(MfgSpeaker.transcript_id == tr.id)
        .order_by(MfgSpeaker.speaker.asc())
    )).scalars().all()
    speakers = [
        {
            "id": sp.id,
            "speaker": sp.speaker,
            "display_name": sp.display_name,
            "color": sp.color,
            "is_active": sp.is_active,
        }
        for sp in spk_rows
    ]

    diar_q = (
        select(MfgDiarization)
        .where(MfgDiarization.transcript_id == tr.id)
        .order_by(MfgDiarization.start_ts.asc())
    )
    if mode:
        diar_q = diar_q.where(MfgDiarization.mode == mode)
    diar_rows = (await session.execute(diar_q)).scalars().all()
    diarization = [
        {
            "id": d.id,
            "start_ts": float(d.start_ts) if d.start_ts is not None else None,
            "end_ts": float(d.end_ts) if d.end_ts is not None else None,
            "speaker": d.speaker,
        }
        for d in diar_rows
    ]

    return {
        **base,
        "segments": segments,
        "speakers": speakers,
        "diarization": diarization,
    }
