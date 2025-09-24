from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.jobs.api import process_diarization
from app.db.session import get_session
from app.db.models import MfgTranscript, MfgFile
from app.schemas.api import DiarizationResponse, DiarizationRequest
from app.core.logger import get_logger
from app.core.auth import require_user
from app.services.audit import audit_log

log = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=DiarizationResponse)
async def upload_diarization(
    background_tasks: BackgroundTasks,
    data: DiarizationRequest,
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
        {"filename": mfg_file.filename, "file_id": mfg_file.id, "meeting_id": data.meeting_id},
    )

    background_tasks.add_task(process_diarization, transcript.id, mfg_file.stored_path)

    await audit_log(user.id, "start_step", "transcript", transcript.id, {"step": "diarization"})

    return DiarizationResponse(
        transcript_id=transcript.id,
        status="processing",
        filename=mfg_file.filename,
    )
