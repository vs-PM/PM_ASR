from __future__ import annotations
from typing import Optional

from sqlalchemy import select, update, func

from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgJob, MfgTranscript, MfgJobEvent

log = get_logger(__name__)

# Шаги пайплайна (для валидации step)
VALID_STEPS = {"diarization", "segmentation", "transcription", "embeddings", "summary"}

# Терминальные статусы job
TERMINAL_STATUSES = {"done", "error", "canceled"}


async def _get_or_create_job(session, tid: int) -> MfgJob:
    job = (await session.execute(
        select(MfgJob).where(MfgJob.transcript_id == tid)
    )).scalars().first()
    if not job:
        job = MfgJob(transcript_id=tid, status="processing", progress=0)
        session.add(job)
        # flush, чтобы у job появились значения по умолчанию (started_at и т.д.)
        await session.flush()
    return job


async def _insert_event(session, *, tid: int, status: str, step: Optional[str], progress: Optional[int] = None, message: Optional[str] = None) -> None:
    session.add(MfgJobEvent(
        transcript_id=tid,
        status=status,       # 'processing' | 'progress' | '<step>_done' | 'done' | 'error' ...
        progress=progress,
        step=step,
        message=message,
    ))
    # событие пишем в той же транзакции, что и апдейт job


async def set_status(tid: int, status: str, *, step: str | None = None, error: str | None = None) -> None:
    """
    Обновить статус job/транскрипта.
    - Если status терминальный → выставляем finished_at=now()
    - Событие в MfgJobEvent записывается в той же транзакции.
    """
    async with async_session() as s:
        job = await _get_or_create_job(s, tid)

        # step: валидируем; если передали что-то странное — не затираем текущий корректный шаг
        if step is not None:
            if step in VALID_STEPS or step == "failed":
                job.step = step
        # статус/ошибка
        job.status = status
        job.error = error

        # если job завершена — фиксируем finished_at
        if status in TERMINAL_STATUSES:
            job.finished_at = func.now()

        s.add(job)

        # дублируем статус в MfgTranscript (для обратной совместимости)
        tr = await s.get(MfgTranscript, tid)
        if tr:
            tr.status = status
            s.add(tr)

        # событие
        await _insert_event(s, tid=tid, status=status, step=job.step, message=error)

        await s.commit()


async def set_progress(tid: int, progress: int, *, step: str | None = None) -> None:
    """
    Обновить прогресс (0..100) и, при необходимости, текущий step.
    Никогда не пишем progress с step='done'.
    """
    p = max(0, min(100, int(progress)))

    async with async_session() as s:
        job = await _get_or_create_job(s, tid)

        # Выбираем корректный step:
        if step is None:
            # если не передан — оставляем текущий, либо 'summary' как дефолт ближе к концу пайплайна
            step_to_set = job.step if job.step in VALID_STEPS else "summary"
        else:
            step_to_set = step if step in VALID_STEPS else (job.step if job.step in VALID_STEPS else "summary")

        job.step = step_to_set
        job.progress = p

        s.add(job)

        # событие 'progress'
        await _insert_event(s, tid=tid, status="progress", step=step_to_set, progress=p)

        await s.commit()


async def get_job(tid: int) -> Optional[MfgJob]:
    async with async_session() as s:
        return (await s.execute(
            select(MfgJob).where(MfgJob.transcript_id == tid)
        )).scalars().first()
