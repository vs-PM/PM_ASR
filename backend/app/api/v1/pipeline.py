from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.db.models import MfgTranscript
from app.services.jobs.api import process_pipeline
from app.schemas.api import PipelineResponse
from app.core.logger import get_logger
from app.core.auth import require_user
from app.services.audit import audit_log

log = get_logger(__name__)
router = APIRouter()


@router.post("/{transcript_id}", response_model=PipelineResponse)
async def run_pipeline(
    background_tasks: BackgroundTasks,
    transcript_id: int,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
):
    transcript = await session.get(MfgTranscript, transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Запускаем фоновой pipeline
    background_tasks.add_task(process_pipeline, transcript_id)
    transcript.status = "transcription_processing"
    session.add(transcript)
    await session.commit()
    await audit_log(user.id, "start_step", "transcript", transcript_id, {"step": "pipeline"})

    return PipelineResponse(
        transcript_id=transcript_id,
        status="processing"
    )
