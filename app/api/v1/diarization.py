import os
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.jobs.api import process_diarization
from app.db.session import get_session
from app.db.models import MfgTranscript
from app.schemas.api import DiarizationResponse
from app.core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=DiarizationResponse)
async def upload_diarization(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    meeting_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    tmp_dir = Path("/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / file.filename

    try:
        tmp_path.write_bytes(await file.read())
        log.info(f"Saved file to {tmp_path}")
    except Exception:
        raise HTTPException(status_code=500, detail="File save failed")

    # Создаём запись в MfgTranscript
    transcript = MfgTranscript(
        filename=file.filename,
        status="processing",
        meeting_id=meeting_id,
        file_path=str(tmp_path)
    )
    session.add(transcript)
    await session.commit()
    await session.refresh(transcript)

    # Фоновая задача
    background_tasks.add_task(process_diarization, transcript.id, str(tmp_path))

    return DiarizationResponse(
        transcript_id=transcript.id,
        status="processing",
        filename=file.filename
    )
