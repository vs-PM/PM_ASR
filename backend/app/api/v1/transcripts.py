from __future__ import annotations
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, func
from app.core.auth import require_user
from app.db.session import async_session
from app.db.models import (
    MfgTranscript, MfgJob, MfgJobEvent, MfgSegment, MfgSummarySection
)

router = APIRouter()

# ---------- LIST ----------
@router.get("/")
async def list_transcripts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    q: Optional[str] = None,                   # поиск по title/filename/meeting_id
    meeting_id: Optional[int] = None,
    status: Optional[str] = None,              # status из MfgJob.status или MfgTranscript.status
    date_from: Optional[str] = None,           # ISO
    date_to: Optional[str] = None,
    _=Depends(require_user),
):
    async with async_session() as s:
        # База — транскрипты; подтягиваем job, если есть
        base = select(MfgTranscript, MfgJob).join(
            MfgJob, MfgJob.transcript_id == MfgTranscript.id, isouter=True
        )

        conds = []
        if meeting_id:
            conds.append(MfgTranscript.meeting_id == meeting_id)
        if q:
            pattern = f"%{q}%"
            conds.append(or_(
                func.coalesce(MfgTranscript.filename, "").ilike(pattern),
                func.cast(MfgTranscript.meeting_id, String).ilike(pattern)  # поиск по meeting_id как строке
            ))
        if status:
            # если job есть — используем job.status, иначе — статус из транскрипта
            conds.append(or_(MfgJob.status == status, and_(MfgJob.status == None, MfgTranscript.status == status)))
        if date_from:
            conds.append(MfgTranscript.created_at >= datetime.fromisoformat(date_from))
        if date_to:
            conds.append(MfgTranscript.created_at <= datetime.fromisoformat(date_to))

        if conds:
            base = base.where(and_(*conds))

        total = (await s.execute(select(func.count(MfgTranscript.id)).where(and_(*conds)) if conds else select(func.count(MfgTranscript.id)))).scalar_one()
        rows = (await s.execute(
            base.order_by(MfgTranscript.created_at.desc()).offset((page-1)*page_size).limit(page_size)
        )).all()

        items = []
        for tr, job in rows:
            items.append({
                "id": tr.id,
                "meeting_id": tr.meeting_id,
                "filename": getattr(tr, "filename", None),
                "status": job.status if job else tr.status,
                "progress": getattr(job, "progress", None),
                "step": getattr(job, "step", None),
                "created_at": tr.created_at,
            })
        return {"items": items, "page": page, "page_size": page_size, "total": total}

# ---------- DETAILS ----------
@router.get("/{tid}")
async def get_transcript(tid: int, include_segments: int = 500, _=Depends(require_user)):
    async with async_session() as s:
        tr = (await s.execute(select(MfgTranscript).where(MfgTranscript.id == tid))).scalar_one_or_none()
        if not tr:
            raise HTTPException(404, "Transcript not found")

        job = (await s.execute(select(MfgJob).where(MfgJob.transcript_id == tid))).scalar_one_or_none()
        summ = (await s.execute(select(MfgSummarySection).where(MfgSummarySection.transcript_id == tid))).scalar_one_or_none()
        segs: List[MfgSegment] = (await s.execute(
            select(MfgSegment).where(MfgSegment.transcript_id == tid).order_by(MfgSegment.start_ts.asc()).limit(include_segments)
        )).scalars().all()

        return {
            "id": tr.id,
            "meeting_id": tr.meeting_id,
            "filename": getattr(tr, "filename", None),
            "status": job.status if job else tr.status,
            "progress": getattr(job, "progress", None),
            "step": getattr(job, "step", None),
            "summary": {
                "draft": getattr(summ, "title", None),
                "final": getattr(summ, "text", None),
            } if summ else None,
            "segments": [
                {
                    "id": sg.id,
                    "speaker": getattr(sg, "speaker", None),
                    "start": float(getattr(sg, "start_ts", 0.0)),
                    "end": float(getattr(sg, "end_ts", 0.0)),
                    "text": sg.text,
                } for sg in segs
            ],
            "created_at": tr.created_at,
            "updated_at": tr.updated_at,
        }

# ---------- STATUS (fallback, если нет WS) ----------
@router.get("/{tid}/status")
async def transcript_status(tid: int, _=Depends(require_user)):
    async with async_session() as s:
        job = (await s.execute(select(MfgJob).where(MfgJob.transcript_id == tid))).scalar_one_or_none()
        if not job:
            # на очень ранних стадиях job мог ещё не создаться — вернём статус транскрипта
            tr = (await s.execute(select(MfgTranscript).where(MfgTranscript.id == tid))).scalar_one_or_none()
            if not tr:
                raise HTTPException(404, "Not found")
            return {"status": tr.status, "progress": None, "step": None, "error": None}
        return {"status": job.status, "progress": job.progress, "step": job.step, "error": job.error}

# ---------- EVENTS (лента) ----------
@router.get("/{tid}/events")
async def transcript_events(tid: int, after_id: Optional[int] = None, limit: int = 200, _=Depends(require_user)):
    async with async_session() as s:
        stmt = select(MfgJobEvent).where(MfgJobEvent.transcript_id == tid).order_by(MfgJobEvent.id.asc())
        if after_id:
            stmt = stmt.where(MfgJobEvent.id > after_id)
        rows = (await s.execute(stmt.limit(limit))).scalars().all()
        return [{
            "id": ev.id,
            "status": ev.status,
            "progress": ev.progress,
            "step": ev.step,
            "message": ev.message,
            "created_at": ev.created_at
        } for ev in rows]
