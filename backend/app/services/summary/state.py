from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import MfgSegment, MfgSummarySection

@dataclass
class ModeState:
    total_segments: int
    transcribed_segments: int
    has_summary_row: bool
    has_summary_text: bool
    status: str  # queued | diarize_done | transcription_done | summary_processing | summary_done

async def get_mode_state(session: AsyncSession, transcript_id: int, mode: str) -> ModeState:
    # 1) считаем сегменты всего и с текстом
    total = (await session.execute(
        select(func.count()).select_from(MfgSegment)
        .where(MfgSegment.transcript_id == transcript_id)
        .where(MfgSegment.mode == mode)
    )).scalar_one()

    transcribed = (await session.execute(
        select(func.count()).select_from(MfgSegment)
        .where(MfgSegment.transcript_id == transcript_id)
        .where(MfgSegment.mode == mode)
        .where(func.length(func.coalesce(MfgSegment.text, "")) > 0)
    )).scalar_one()

    # 2) смотрим секцию summary (финальную idx=1, и, на всякий случай, любую)
    row = (await session.execute(
        select(MfgSummarySection)
        .where(MfgSummarySection.transcript_id == transcript_id)
        .where(MfgSummarySection.mode == mode)
        .where(MfgSummarySection.idx == 1)
        .limit(1)
    )).scalar_one_or_none()

    if row is None:
        row = (await session.execute(
            select(MfgSummarySection)
            .where(MfgSummarySection.transcript_id == transcript_id)
            .where(MfgSummarySection.mode == mode)
            .order_by(MfgSummarySection.idx.asc())
            .limit(1)
        )).scalar_one_or_none()

    has_row = row is not None
    has_text = bool((row.text or "").strip()) if row else False

    # 3) вычисляем статус
    if has_text:
        status = "summary_done"
    elif total == 0:
        status = "queued"
    elif transcribed == 0:
        status = "diarize_done"
    elif transcribed < total:
        # можно было бы вернуть transcription_in_progress, но в ваших терминах — оставим как diarize_done
        status = "diarize_done"
    else:
        # все сегменты имеют текст → либо ждём, либо уже запустили summary
        status = "summary_processing" if has_row else "transcription_done"

    return ModeState(
        total_segments=total,
        transcribed_segments=transcribed,
        has_summary_row=has_row,
        has_summary_text=has_text,
        status=status,
    )
