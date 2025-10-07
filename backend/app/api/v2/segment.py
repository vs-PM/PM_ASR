from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func, asc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_user
from app.core.logger import get_logger
from app.db.session import get_session, async_session
from app.db.models import MfgTranscript, MfgFile, MfgDiarization, MfgSpeaker, MfgSegment
from app.schemas.v2 import SegmentStartIn, SegmentStartOut, SegmentStateOut, TranscriptionStartOut, SegmentMode
from app.schemas.v2 import TranscriptV2Result, SpeakerItem as SP, DiarItem as DI, SegmentTextItem as STI
from app.services.jobs.api import process_diarization, process_segmentation, process_pipeline
from app.services.jobs.steps import pipeline as pipeline_step

log = get_logger(__name__)
router = APIRouter()

async def _run_full_segmentation(transcript_id: int, audio_path: str, file_id: int, mode: str) -> int:
    import torchaudio
    try:
        info = torchaudio.info(audio_path)
        dur = max(0.0, float(info.num_frames) / float(info.sample_rate))
    except Exception:
        log.exception("Cannot probe duration; use 0s")
        dur = 0.0
    async with async_session() as s:
        s.add(MfgDiarization(
            transcript_id=transcript_id, mode=mode, speaker="SPEECH",
            start_ts=0.0, end_ts=dur, file_path=audio_path,
        ))
        tr = await s.get(MfgTranscript, transcript_id)
        if tr:
            tr.status = "diarization_done"
            s.add(tr)
        await s.commit()
    return 1

async def _wrap_segmentation_and_mark_done(mode: str, transcript_id: int) -> None:
    """
    Фоновая нарезка для выбранного режима. По завершении → status='diarization_done'.
    """
    try:
        # 1) Вытащим путь: сначала из MfgTranscript.file_path, если пусто — из MfgFile.stored_path
        async with async_session() as s:
            tr = await s.get(MfgTranscript, transcript_id)
            if not tr:
                raise RuntimeError(f"Transcript {transcript_id} not found")

            audio_path = getattr(tr, "file_path", None)
            if not audio_path and getattr(tr, "file_id", None):
                f = await s.get(MfgFile, tr.file_id)
                if f and getattr(f, "stored_path", None):
                    audio_path = f.stored_path

        if not audio_path:
            raise RuntimeError("Audio file path is not set")

        # 2) Запустим нужный шаг
        if mode == "diarize":
            from app.services.jobs.steps import diarization as diar_step
            chunks = await diar_step.run(transcript_id, audio_path)
        else:
            from app.services.jobs.steps import segmentation as seg_step
            chunks = await seg_step.run(transcript_id, audio_path, mode=mode)

        log.info("Segmentation done: tid=%s mode=%s chunks=%s", transcript_id, mode, chunks)

        # 3) Поставим статус
        async with async_session() as s:
            tr = await s.get(MfgTranscript, transcript_id)
            if tr:
                tr.status = "diarization_done"
                s.add(tr)
                await s.commit()

    except Exception:
        log.exception("Segmentation failed: tid=%s mode=%s", transcript_id, mode)
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

    # 2) привязки: file_id/filename, meeting_id := file_id
    changed = False
    if tr.file_id != f.id:
        tr.file_id = f.id
        changed = True
    if not tr.filename and getattr(f, "original_name", None):
        tr.filename = f.original_name
        changed = True
    if not getattr(tr, "file_path", None) and getattr(f, "stored_path", None):
        tr.file_path = f.stored_path
        changed = True
    if tr.meeting_id != f.id:
        tr.meeting_id = f.id   # пишем meeting_id=file_id
        changed = True
    if changed:
        session.add(tr)
        await session.commit()
    
     # 3) если уже есть чанки для этого режима
    existing = (await session.execute(
        select(func.count(MfgDiarization.id))
        .where(MfgDiarization.transcript_id == tr.id, MfgDiarization.mode == data.mode)
    )).scalar_one() or 0

    if existing > 0 and not data.overwrite:
        # мягкий отказ с подсказкой
        raise HTTPException(
            status_code=409,
            detail={"code": "already_segmented", "mode": data.mode, "chunks": int(existing)}
        )

    if existing > 0 and data.overwrite:
        # чистим старые нарезки в этом режиме
        await session.execute(
            delete(MfgDiarization)
            .where(MfgDiarization.transcript_id == tr.id, MfgDiarization.mode == data.mode)
        )
        await session.commit()

    # 4) фоновая нарезка
    background_tasks.add_task(_wrap_segmentation_and_mark_done, data.mode, tr.id)

    return SegmentStartOut(transcript_id=tr.id, status="processing", mode=data.mode)

@router.get("/{transcript_id}")
async def get_segmentation_state(
    transcript_id: int,
    mode: SegmentMode = "diarize",
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
) -> SegmentStateOut:
    tr = await session.get(MfgTranscript, transcript_id)
    if not tr or tr.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcript not found")

    total = (await session.execute(
        select(func.count(MfgDiarization.id))
        .where(MfgDiarization.transcript_id == transcript_id, MfgDiarization.mode == mode)
    )).scalar_one() or 0

    return SegmentStateOut(transcript_id=transcript_id, status=tr.status, chunks=int(total))

@router.post("/transcription/{transcript_id}")
async def start_transcription_from_segments(
    transcript_id: int,
    background_tasks: BackgroundTasks,
    mode: SegmentMode = "diarize",
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
) -> TranscriptionStartOut:
    tr = await session.get(MfgTranscript, transcript_id)
    if not tr or tr.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Можно валидировать наличие чанков в этом режиме
    exists = (await session.execute(
        select(func.count(MfgDiarization.id))
        .where(MfgDiarization.transcript_id == transcript_id, MfgDiarization.mode == mode)
    )).scalar_one() or 0
    if exists == 0:
        raise HTTPException(status_code=400, detail=f"No segments for mode={mode}")

    background_tasks.add_task(pipeline_step.run, transcript_id, "ru", mode)
    tr.status = "transcription_processing"
    session.add(tr); await session.commit()
    return TranscriptionStartOut(transcript_id=transcript_id, status="transcription_processing")


@router.get("/{transcript_id}/result")
async def get_full_result(
    transcript_id: int,
    mode: SegmentMode = "diarize",
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
) -> TranscriptV2Result:
    # 1) транскрипт
    tr = await session.get(MfgTranscript, transcript_id)
    if not tr or tr.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # 2) диаризация
    diar_rows = (await session.execute(
        select(MfgDiarization)
        .where(MfgDiarization.transcript_id == transcript_id, MfgDiarization.mode == mode)
        .order_by(asc(MfgDiarization.start_ts))
    )).scalars().all()
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
            .where(
                MfgSegment.transcript_id == transcript_id,
                MfgSegment.mode == mode,
            )
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