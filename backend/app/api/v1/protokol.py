from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import MfgTranscript, MfgFile
from app.schemas.api import ProtokolResponse, ProtokolRequest
from app.services.jobs.api import process_protokol
from app.core.logger import get_logger
from app.core.auth import require_user
from app.services.audit import audit_log

log = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=ProtokolResponse)
async def upload_and_run_protokol(
    background_tasks: BackgroundTasks,
    data: ProtokolRequest,
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
            "seg": data.seg,
        },
    )

    background_tasks.add_task(
        process_protokol,
        transcript.id,
        mfg_file.stored_path,
        "ru",
        "json",
        data.seg,
    )

    await audit_log(
        user.id,
        "start_protokol",
        "transcript",
        transcript.id,
        {"lang": "ru", "format": "json", "seg": data.seg},
    )

    return ProtokolResponse(
        transcript_id=transcript.id,
        status="processing",
        filename=mfg_file.filename,
    )
