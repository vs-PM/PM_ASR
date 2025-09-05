from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.db.models import MfgTranscript
from app.services.jobs.api import process_pipeline
from app.schemas.api import PipelineResponse
from app.core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/{transcript_id}", response_model=PipelineResponse)
async def run_pipeline(
    background_tasks: BackgroundTasks,
    transcript_id: int,
    session: AsyncSession = Depends(get_session)
):
    transcript = await session.get(MfgTranscript, transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Запускаем фоновой pipeline
    background_tasks.add_task(process_pipeline, transcript_id)
    transcript.status = "pipeline_processing"
    session.add(transcript)
    await session.commit()

    return PipelineResponse(
        transcript_id=transcript_id,
        status="processing"
    )
