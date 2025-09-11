from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.db.models import MfgTranscript
from app.services.jobs.api import process_embeddings
from app.schemas.api import EmbeddingsResponse
from app.core.logger import get_logger
from app.core.auth import require_user
from app.services.audit import audit_log

log = get_logger(__name__)
router = APIRouter()


@router.post("/{transcript_id}", response_model=EmbeddingsResponse)
async def generate_embeddings(
    background_tasks: BackgroundTasks,
    transcript_id: int,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
):
    transcript = await session.get(MfgTranscript, transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Запускаем фоновой процесс
    background_tasks.add_task(process_embeddings, transcript_id)
    transcript.status = "embeddings_processing"
    session.add(transcript)
    await session.commit()
    await audit_log(user.id, "start_step", "transcript", transcript_id, {"step": "embeddings"})

    return EmbeddingsResponse(
        transcript_id=transcript_id,
        status="processing"
    )
