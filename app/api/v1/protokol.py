from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import MfgTranscript
from app.schemas.api import ProtokolResponse
from app.services.jobs.api import process_protokol
from app.core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()

@router.post("/", response_model=ProtokolResponse)
async def upload_and_run_protokol(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    meeting_id: int = Query(...),
    seg: str = Query("diarize", pattern="^(diarize|vad|fixed)$"),
    session: AsyncSession = Depends(get_session),
):
    # 1) сохраняем временный файл
    tmp_dir = Path("/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / file.filename

    try:
        tmp_path.write_bytes(await file.read())
        log.info("Saved upload to %s", tmp_path)
    except Exception:
        log.exception("Failed to save uploaded file")
        raise HTTPException(status_code=500, detail="File save failed")

    # 2) создаём запись транскрипта
    transcript = MfgTranscript(
        filename=file.filename,
        status="processing",
        meeting_id=meeting_id,
        file_path=str(tmp_path),
    )
    session.add(transcript)
    await session.commit()
    await session.refresh(transcript)

    # 3) запускаем комбинированный пайплайн в фоне
    # Язык/формат можно будет параметризовать, пока фиксируем RU+JSON.
    background_tasks.add_task(
        process_protokol,
        transcript.id,
        str(tmp_path),
        "ru",
        "json",
        seg,
    )

    return ProtokolResponse(
        transcript_id=transcript.id,
        status="processing",
        filename=file.filename,
    )
