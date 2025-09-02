from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import MfgTranscript
from app.background import process_embeddings
from app.schemas import EmbeddingsResponse
from app.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/{transcript_id}", response_model=EmbeddingsResponse)
async def generate_embeddings(
    background_tasks: BackgroundTasks,
    transcript_id: int,
    session: AsyncSession = Depends(get_session)
):
    transcript = await session.get(MfgTranscript, transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Запускаем фоновой процесс
    background_tasks.add_task(process_embeddings, transcript_id)
    transcript.status = "embeddings_processing"
    session.add(transcript)
    await session.commit()

    return EmbeddingsResponse(
        transcript_id=transcript_id,
        status="processing"
    )
