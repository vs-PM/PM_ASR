from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import MfgTranscript, MfgSummarySection, MfgActionItem
from app.background import process_summary
from app.logger import get_logger
from app.schemas import SummaryStartResponse, SummaryGetResponse, SummarySection, ActionItem

log = get_logger(__name__)
router = APIRouter()

@router.post("/{transcript_id}", response_model=SummaryStartResponse)
async def run_summary(
    background_tasks: BackgroundTasks,
    transcript_id: int,
    lang: str = Query("ru"),
    format_: str = Query("json", alias="format"),
    session: AsyncSession = Depends(get_session),
):
    trs = await session.get(MfgTranscript, transcript_id)
    if not trs:
        raise HTTPException(status_code=404, detail="Transcript not found")

    trs.status = "summary_processing"
    session.add(trs)
    await session.commit()

    background_tasks.add_task(process_summary, transcript_id, lang, format_)
    return SummaryStartResponse(transcript_id=transcript_id, status="processing")

@router.get("/{transcript_id}", response_model=SummaryGetResponse)
async def get_summary(
    transcript_id: int,
    session: AsyncSession = Depends(get_session),
):
    trs = await session.get(MfgTranscript, transcript_id)
    if not trs:
        raise HTTPException(status_code=404, detail="Transcript not found")

    sections = (
        await session.execute(
            select(MfgSummarySection)
            .where(MfgSummarySection.transcript_id == transcript_id)
            .order_by(MfgSummarySection.idx)
        )
    ).scalars().all()

    items = (
        await session.execute(
            select(MfgActionItem)
            .where(MfgActionItem.transcript_id == transcript_id)
            .order_by(MfgActionItem.id)
        )
    ).scalars().all()

    return SummaryGetResponse(
        transcript_id=transcript_id,
        status=trs.status,
        sections=[
            SummarySection(
                idx=s.idx,
                start_ts=s.start_ts,
                end_ts=s.end_ts,
                title=s.title,
                text=s.text,
            ) for s in sections
        ],
        action_items=[
            ActionItem(
                id=a.id,
                assignee=a.assignee,
                due_date=a.due_date.isoformat() if a.due_date else None,
                task=a.task,
                priority=a.priority,
            ) for a in items
        ]
    )
