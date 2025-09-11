import os
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Query, Depends
from app.schemas.api import RecognizeResponse
from app.services.jobs.api import process_transcription
from app.db.session import async_session, get_session
from app.db.models import MfgTranscript
from app.core.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import require_user
from app.services.audit import audit_log

log = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=RecognizeResponse)
async def upload_transcription(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    meeting_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
):
    tmp_dir = Path("/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / file.filename

    try:
        # Сохраняем файл
        content = await file.read()
        tmp_path.write_bytes(content)
        log.info(f"Файл '{file.filename}' загружен и сохранен во временную директорию: {tmp_path}")
    except Exception:
        log.exception("Ошибка при сохранении загруженного файла")
        raise HTTPException(status_code=500, detail="Не удалось сохранить файл")

    # Создаём запись в БД
    transcript = MfgTranscript(
        filename=file.filename,
        status="processing",
        meeting_id=meeting_id,
        file_path=str(tmp_path)
    )
    session.add(transcript)
    await session.commit()
    await session.refresh(transcript)
    await audit_log(user.id, "upload", "transcript", transcript.id, {
        "filename": file.filename
    })
    log.info(f"Создана запись транскрипта id={transcript.id}, meeting_id={meeting_id}, статус={transcript.status}")

    # Фоновая задача
    background_tasks.add_task(process_transcription, transcript.id, str(tmp_path))
    log.info(f"Фоновая задача транскрипции добавлена для transcript_id={transcript.id}")
    await audit_log(user.id, "start_step", "transcript", transcript.id, {
        "step": "transcription"
    })

    return RecognizeResponse(
        transcript_id=transcript.id,
        filename=file.filename,
        status="processing"
    )


@router.get("/{transcript_id}")
async def get_transcript(transcript_id: int, session: AsyncSession = Depends(get_session)):
    transcript = await session.get(MfgTranscript, transcript_id)
    if not transcript:
        log.warning(f"Попытка получить несуществующий transcript_id={transcript_id}")
        raise HTTPException(status_code=404, detail="Транскрипт не найден")
    log.info(f"Получена запись транскрипта id={transcript.id}, статус={transcript.status}")
    return {
        "id": transcript.id,
        "status": transcript.status,
        "processed_text": transcript.processed_text,
        "raw_text": transcript.raw_text
    }
