# app/api/v2/segment.py
from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_user
from app.core.logger import get_logger
from app.db.session import get_session, async_session
from app.db.models import MfgTranscript, MfgFile, MfgDiarization, MfgSpeaker, MfgSegment
from app.schemas.v2 import SegmentStartIn, SegmentStartOut, SegmentStateOut, TranscriptionStartOut
from app.schemas.v2 import TranscriptV2Result, SpeakerItem as SP, DiarItem as DI, SegmentTextItem as STI
from app.services.jobs.api import process_diarization, process_segmentation, process_pipeline

log = get_logger(__name__)
router = APIRouter()

async def _run_full_segmentation(transcript_id: int, audio_path: str, file_id: int) -> int:
    import torchaudio
    try:
        info = torchaudio.info(audio_path)
        dur = max(0.0, float(info.num_frames) / float(info.sample_rate))
    except Exception:
        log.exception("Cannot probe duration; use 0s")
        dur = 0.0
    async with async_session() as s:
        s.add(MfgDiarization(
            transcript_id=transcript_id, speaker="SPEECH",
            start_ts=0.0, end_ts=dur, file_path=audio_path,
        ))
        tr = await s.get(MfgTranscript, transcript_id)
        if tr:
            tr.status = "diarization_done"
            s.add(tr)
        await s.commit()
    return 1

async def _wrap_segmentation_and_mark_done(mode: str, transcript_id: int, audio_path: str, file_id: int) -> None:
    try:
        if mode == "diarize":
            chunks = await process_diarization(transcript_id, audio_path)
        elif mode in ("vad", "fixed"):
            chunks = await process_segmentation(transcript_id, audio_path, mode)
        elif mode == "full":
            chunks = await _run_full_segmentation(transcript_id, audio_path, file_id)
        else:
            log.error("Unknown mode: %s", mode)
            chunks = 0
        async with async_session() as s:
            tr = await s.get(MfgTranscript, transcript_id)
            if tr:
                tr.status = "diarization_done"
                s.add(tr)
                await s.commit()
        log.info("Segmentation(%s) done: tid=%s chunks=%s", mode, transcript_id, chunks)
    except Exception:
        log.exception("Segmentation(%s) failed: tid=%s", mode, transcript_id)
        async with async_session() as s:
            tr = await s.get(MfgTranscript, transcript_id)
            if tr:
                tr.status = "error"
                s.add(tr)
                await s.commit()

@router.post("")  # /api/v2/segment (без завершающего слэша)
async def start_segmentation(
    data: SegmentStartIn,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
) -> SegmentStartOut:
    # 0) транскрипт по PK
    tr = await session.get(MfgTranscript, data.id)
    if not tr or tr.user_id != user.id:
        raise HTTPException(status_code=404, detail="transcript not found")

    # 1) файл принадлежит пользователю?
    f = (
        await session.execute(
            select(MfgFile).where(MfgFile.id == data.file_id, MfgFile.user_id == user.id)
        )
    ).scalars().first()
    if not f:
        raise HTTPException(status_code=404, detail="file not found")

    # 2) привязки: file_id/filename, meeting_id := file_id (как договорились)
    changed = False
    if tr.file_id != f.id:
        tr.file_id = f.id
        changed = True
    if not tr.filename:
        tr.filename = f.filename
        changed = True
    if tr.meeting_id != f.id:
        tr.meeting_id = f.id   # пишем meeting_id=file_id
        changed = True
    if changed:
        session.add(tr)
        await session.commit()

    # 3) фоновая нарезка
    background_tasks.add_task(_wrap_segmentation_and_mark_done, data.mode, tr.id, f.stored_path, f.id)

    return SegmentStartOut(transcript_id=tr.id, status="processing", mode=data.mode)

@router.get("/{transcript_id}")
async def get_segmentation_state(
    transcript_id: int,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
) -> SegmentStateOut:
    tr = await session.get(MfgTranscript, transcript_id)
    if not tr or tr.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcript not found")

    total = (
        await session.execute(
            select(func.count(MfgDiarization.id)).where(MfgDiarization.transcript_id == transcript_id)
        )
    ).scalar_one() or 0

    return SegmentStateOut(transcript_id=transcript_id, status=tr.status, chunks=int(total))

@router.post("/transcription/{transcript_id}")
async def start_transcription_from_segments(
    transcript_id: int,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
) -> TranscriptionStartOut:
    tr = await session.get(MfgTranscript, transcript_id)
    if not tr or tr.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcript not found")

    background_tasks.add_task(process_pipeline, transcript_id)
    tr.status = "transcription_processing"
    session.add(tr)
    await session.commit()
    return TranscriptionStartOut(transcript_id=transcript_id, status="transcription_processing")


@router.get("/{transcript_id}/result")
async def get_full_result(
    transcript_id: int,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
) -> TranscriptV2Result:
    # 1) транскрипт
    tr = await session.get(MfgTranscript, transcript_id)
    if not tr or tr.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # 2) диаризация
    diar_rows = (
        await session.execute(
            select(MfgDiarization)
            .where(MfgDiarization.transcript_id == transcript_id)
            .order_by(asc(MfgDiarization.start_ts))
        )
    ).scalars().all()
    diar = [
        DI(id=row.id, start_ts=row.start_ts, end_ts=row.end_ts, speaker=getattr(row, "speaker", None))
        for row in diar_rows
    ]

    # 3) спикеры (если есть)
    sp_rows = (
        await session.execute(
            select(MfgSpeaker).where(MfgSpeaker.transcript_id == transcript_id).order_by(asc(MfgSpeaker.id))
        )
    ).scalars().all()
    speakers = [
        SP(
            id=row.id,
            speaker=row.speaker,
            display_name=getattr(row, "display_name", None),
            color=getattr(row, "color", None),
            is_active=bool(getattr(row, "is_active", True)),
        )
        for row in sp_rows
    ]

    # 4) текстовые сегменты (опционально)
    segments: list[STI] = []

    seg_rows = (
        await session.execute(
            select(MfgSegment)
            .where(MfgSegment.transcript_id == transcript_id)
            .order_by(asc(MfgSegment.start_ts))
        )
    ).scalars().all()
    segments = [
        STI(
            id=row.id,
            start_ts=getattr(row, "start_ts", None),
            end_ts=getattr(row, "end_ts", None),
            text=getattr(row, "text", ""),
            speaker=getattr(row, "speaker", None),
            lang=getattr(row, "lang", None),
        )
        for row in seg_rows
    ]

    # 5) текст из транскрипта (любой доступный)
    text = getattr(tr, "processed_text", None) or getattr(tr, "raw_text", None) or getattr(tr, "text", None)

    return TranscriptV2Result(
        transcript_id=tr.id,
        status=tr.status,
        filename=tr.filename,
        file_id=tr.file_id,
        created_at=str(tr.created_at) if getattr(tr, "created_at", None) else None,
        updated_at=str(tr.updated_at) if getattr(tr, "updated_at", None) else None,
        text=text,
        diarization=diar,
        speakers=speakers,
        segments=segments,
    )