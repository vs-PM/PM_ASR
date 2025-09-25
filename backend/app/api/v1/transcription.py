from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.api import RecognizeResponse, RecognizeRequest
from app.services.jobs.api import process_transcription
from app.db.session import get_session
from app.db.models import MfgTranscript, MfgFile
from app.core.logger import get_logger
from app.core.auth import require_user
from app.services.audit import audit_log

log = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=RecognizeResponse)
async def upload_transcription(
    background_tasks: BackgroundTasks,
    data: RecognizeRequest,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
):
    result = await session.execute(
        select(MfgFile).where(MfgFile.id == data.file_id, MfgFile.user_id == user.id)
    )
    mfg_file = result.scalar_one_or_none()
    if not mfg_file:
        raise HTTPException(status_code=404, detail="File not found")

    transcript = MfgTranscript(
        filename=mfg_file.filename,
        status="processing",
        meeting_id=data.meeting_id,
        file_path=mfg_file.stored_path,
        file_id=mfg_file.id,
        user_id=user.id,
    )
    session.add(transcript)
    await session.commit()
    await session.refresh(transcript)
    await audit_log(
        user.id,
        "upload",
        "transcript",
        transcript.id,
        {
            "filename": mfg_file.filename,
            "file_id": mfg_file.id,
            "meeting_id": data.meeting_id,
        },
    )
    log.info(
        "Создана запись транскрипта id=%s, meeting_id=%s, статус=%s",
        transcript.id,
        data.meeting_id,
        transcript.status,
    )

    background_tasks.add_task(process_transcription, transcript.id, mfg_file.stored_path)
    log.info("Фоновая задача транскрипции добавлена для transcript_id=%s", transcript.id)
    await audit_log(
        user.id,
        "start_step",
        "transcript",
        transcript.id,
        {"step": "transcription"},
    )

    return RecognizeResponse(
        transcript_id=transcript.id,
        filename=mfg_file.filename,
        status="processing",
    )


@router.get("/{transcript_id}")
async def get_transcript(transcript_id: int, session: AsyncSession = Depends(get_session)):
    transcript = await session.get(MfgTranscript, transcript_id)
    if not transcript:
        log.warning("Попытка получить несуществующий transcript_id=%s", transcript_id)
        raise HTTPException(status_code=404, detail="Транскрипт не найден")
    log.info("Получена запись транскрипта id=%s, статус=%s", transcript.id, transcript.status)
    return {
        "id": transcript.id,
        "status": transcript.status,
        "processed_text": transcript.processed_text,
        "raw_text": transcript.raw_text,
    }
