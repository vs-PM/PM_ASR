from __future__ import annotations

import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import MfgTranscript, MfgSummarySection
from app.services.jobs.api import process_summary
from app.services.summary.state import get_mode_state
from app.core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


# === Pydantic схемы (минимальные, чтобы не тащить внешние зависимости) ===

class SummaryStartResponse(BaseModel):
    transcript_id: int
    status: str = "summary_processing"


class SummaryGetResponse(BaseModel):
    transcript_id: int
    status: str  # "summary_processing" | "summary_done"
    text: str


# === POST: запустить генерацию summary для заданного mode ===

@router.post("/{transcript_id}", response_model=SummaryStartResponse)
async def start_summary(
    background_tasks: BackgroundTasks,
    transcript_id: int,
    lang: str = Query("ru"),
    format_: str = Query("md", alias="format"),  # <-- используем format_
    mode: str = Query("diarize"),
    session: AsyncSession = Depends(get_session),
):
    # 1) транскрипт должен существовать
    trs = await session.get(MfgTranscript, transcript_id)
    if not trs:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # 2) статус процесса
    trs.status = "summary_processing"
    session.add(trs)

    # 3) удаляем только старые секции ЭТОГО mode (а не всех mode)
    await session.execute(
        delete(MfgSummarySection)
        .where(MfgSummarySection.transcript_id == transcript_id)
        .where(MfgSummarySection.mode == mode)
    )
    await session.commit()

    # 4) создаём пустую «контейнерную» запись idx=1 под финальный текст этого mode
    session.add(MfgSummarySection(
        transcript_id=transcript_id,
        idx=1,
        start_ts=0.0,
        end_ts=0.0,
        title="draft",
        text="",
        mode=mode,
    ))
    await session.commit()

    # 5) запускаем фоновую задачу
    background_tasks.add_task(process_summary, transcript_id, lang, format_, mode)
    return SummaryStartResponse(transcript_id=transcript_id, status="summary_processing")


# === GET: получить summary для mode (без 404, если секции нет/пустая) ===
@router.get("/{transcript_id}", response_model=SummaryGetResponse)
async def get_summary(
    transcript_id: int,
    mode: str = Query("diarize"),
    session: AsyncSession = Depends(get_session),
):
    # 1) транскрипт должен существовать (единственный валидный 404)
    trs = await session.get(MfgTranscript, transcript_id)
    if not trs:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # 2) считаем состояние по режиму
    st = await get_mode_state(session, transcript_id, mode)

    # 3) формируем ответ
    if st.status == "summary_done":
        row_text = (await session.execute(
            select(MfgSummarySection.text)
            .where(MfgSummarySection.transcript_id == transcript_id)
            .where(MfgSummarySection.mode == mode)
            .where(MfgSummarySection.idx == 1)
            .limit(1)
        )).scalar_one_or_none()
        if row_text is None:
            # fallback: если idx=1 нет, взять любую
            row_text = (await session.execute(
                select(MfgSummarySection.text)
                .where(MfgSummarySection.transcript_id == transcript_id)
                .where(MfgSummarySection.mode == mode)
                .order_by(MfgSummarySection.idx.asc())
                .limit(1)
            )).scalar_one_or_none() or ""
        return SummaryGetResponse(
            transcript_id=transcript_id,
            status="summary_done",
            text=row_text or "",
        )

    # иначе — не кидаем 404, возвращаем статус и пустой текст
    return SummaryGetResponse(
        transcript_id=transcript_id,
        status=st.status,  # queued | diarize_done | transcription_done | summary_processing
        text="",
    )