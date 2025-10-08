from __future__ import annotations
import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth import require_user
from app.core.logger import get_logger
from app.db.session import get_session
from app.db.models import MfgTranscript
from app.schemas.v2 import SegmentMode
from app.services.jobs.api import process_embeddings, process_summary

log = get_logger(__name__)
router = APIRouter()

class EmbedSumIn(BaseModel):
    mode: SegmentMode = Field(default="diarize")
    lang: str = Field(default="ru")
    format: str = Field(default="md")

class EmbedSumOut(BaseModel):
    transcript_id: int
    mode: SegmentMode
    status: str = "processing"
    step: str = "embeddings"

@router.post("/transcripts/{transcript_id}/embedsum", response_model=EmbedSumOut)
async def start_embedsum(
    transcript_id: int,
    payload: EmbedSumIn,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_user),
):
    tr = await session.get(MfgTranscript, transcript_id)
    if not tr or tr.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcript not found")

    async def _chain():
        try:
            await process_embeddings(transcript_id, mode=payload.mode)
        except Exception:
            log.exception("Embeddings failed: tid=%s mode=%s", transcript_id, payload.mode)
        try:
            await process_summary(transcript_id, lang=payload.lang, format_=payload.format, mode=payload.mode)
        except Exception:
            log.exception("Summary failed: tid=%s mode=%s", transcript_id, payload.mode)

    # не блокируем ответ
    asyncio.create_task(_chain())

    return EmbedSumOut(transcript_id=transcript_id, mode=payload.mode)
