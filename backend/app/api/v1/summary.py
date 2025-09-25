from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import MfgTranscript, MfgSummarySection
from app.services.jobs.api import process_summary
from app.core.logger import get_logger
from app.schemas.api import SummaryStartResponse, SummaryGetResponse
from app.core.auth import require_user
from app.services.audit import audit_log

log = get_logger(__name__)
router = APIRouter()


@router.post("/{transcript_id}", response_model=SummaryStartResponse)
async def run_summary(
    background_tasks: BackgroundTasks,
    transcript_id: int,
    lang: str = Query("ru"),
    format_: str = Query("text", alias="format"),
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
):
    # 1) убедимся, что есть транскрипт
    trs = await session.get(MfgTranscript, transcript_id)
    if not trs:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # 2) статус процесса
    trs.status = "summary_processing"
    session.add(trs)

    # 3) очистим все старые секции для данного transcript_id
    await session.execute(
        delete(MfgSummarySection).where(MfgSummarySection.transcript_id == transcript_id)
    )
    await session.commit()

    # 4) создаём пустую запись idx=0 (контейнер для текста)
    section = MfgSummarySection(
        transcript_id=transcript_id,
        idx=0,
        start_ts=0.0,
        end_ts=0.0,
        title="draft",
        text="",
    )
    session.add(section)
    await session.commit()

    # 5) запустим фон
    background_tasks.add_task(process_summary, transcript_id, lang, format_)
    await audit_log(user.id, "start_step", "transcript", transcript_id, {"step": "summary", "lang": lang, "format": format_})
    
    return SummaryStartResponse(transcript_id=transcript_id, status="processing")


@router.get("/{transcript_id}", response_model=SummaryGetResponse)
async def get_summary(
    transcript_id: int,
    session: AsyncSession = Depends(get_session),
):
    trs = await session.get(MfgTranscript, transcript_id)
    if not trs:
        raise HTTPException(status_code=404, detail="Transcript not found")

    section = (
        await session.execute(
            select(MfgSummarySection)
            .where(MfgSummarySection.transcript_id == transcript_id)
            .where(MfgSummarySection.idx == 1)
            .limit(1)
        )
    ).scalar_one_or_none()

    text = section.text if section else ""
    status = trs.status or ("summary_done" if text else "summary_processing")

    return SummaryGetResponse(
        transcript_id=transcript_id,
        status=status,
        text=text or "",
    )
