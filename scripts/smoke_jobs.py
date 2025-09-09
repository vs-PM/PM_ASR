# scripts/smoke_jobs.py
#!/usr/bin/env python3
"""
Smoke test for PM_ASR jobs pipeline.

Запускает полный протокол (diarize/segment -> ASR -> embeddings -> summary)
на указанном аудио и печатает прогресс/итоговую сводку в консоль.

Пример:
    python scripts/smoke_jobs.py --file "vvs-n0n\\32.m4a" --seg-mode fixed
"""

from __future__ import annotations

import sys
import os
import time
import argparse
import asyncio
import pathlib
from typing import Optional

# --- Добавляем КОРЕНЬ репозитория в sys.path (родитель папки "app") ---
THIS = pathlib.Path(__file__).resolve()
ROOT = THIS.parents[1] if (THIS.parents[1] / "app").is_dir() else THIS.parents[0]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- Импорты приложения ---
from sqlalchemy import select, insert, func
from app.db.session import async_session
from app.db.models import (
    MfgTranscript,
    MfgJob,
    MfgJobEvent,
    MfgSegment,
    MfgDiarization,
    MfgEmbedding,
    MfgSummarySection,
)
from app.services.jobs.api import process_protokol


# ---------- Утилиты ----------

def _normalize_path(p: str) -> pathlib.Path:
    """Пытаемся найти файл относительно корня, учитывая обратные слэши."""
    candidates = []
    # как есть
    candidates.append(pathlib.Path(p))
    # заменить \ на /
    candidates.append(pathlib.Path(p.replace("\\", os.sep)))
    # относит. к корню
    candidates.append((ROOT / p.replace("\\", os.sep)))
    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(f"Audio file not found by any of: {', '.join(map(str, candidates))}")


async def _fetch_job(tid: int) -> Optional[MfgJob]:
    async with async_session() as s:
        return (await s.execute(
            select(MfgJob).where(MfgJob.transcript_id == tid)
        )).scalars().first()


async def _counts(tid: int) -> dict:
    async with async_session() as s:
        segs = (await s.execute(select(func.count()).select_from(MfgSegment).where(MfgSegment.transcript_id == tid))).scalar_one()
        diars = (await s.execute(select(func.count()).select_from(MfgDiarization).where(MfgDiarization.transcript_id == tid))).scalar_one()
        embs = (await s.execute(select(func.count()).select_from(MfgEmbedding).join(MfgSegment, MfgEmbedding.segment_id == MfgSegment.id).where(MfgSegment.transcript_id == tid))).scalar_one()
        summ = (await s.execute(select(func.count()).select_from(MfgSummarySection).where(MfgSummarySection.transcript_id == tid))).scalar_one()
        return {"segments": segs, "diar_chunks": diars, "embeddings": embs, "summary_sections": summ}


async def _tail_events(tid: int, limit: int = 10) -> list[tuple]:
    async with async_session() as s:
        rows = (await s.execute(
            select(MfgJobEvent.status, MfgJobEvent.progress, MfgJobEvent.step, MfgJobEvent.created_at)
            .where(MfgJobEvent.transcript_id == tid)
            .order_by(MfgJobEvent.id.desc())
            .limit(limit)
        )).all()
        return list(reversed(rows))  # хронологически


def _print_header(args, audio_path: pathlib.Path):
    print("=" * 80)
    print("PM_ASR smoke run")
    print("- file:       ", audio_path)
    print("- seg_mode:   ", args.seg_mode)
    print("- lang/format:", args.lang, "/", args.format)
    print("- timeout(s): ", args.timeout, "  poll(s):", args.poll)
    print("=" * 80, flush=True)


def _print_progress_line(status: str, progress: int, step: Optional[str]):
    bar_w = 30
    p = max(0, min(100, int(progress or 0)))
    filled = int(bar_w * p / 100)
    bar = "█" * filled + "·" * (bar_w - filled)
    txt = f"[{bar}] {p:3d}%  status={status:<22} step={step or '-'}"
    print("\r" + txt[:120], end="", flush=True)


# ---------- Основной сценарий ----------

async def main():
    parser = argparse.ArgumentParser(description="PM_ASR smoke test runner")
    parser.add_argument("--file", required=True, help="Путь к аудио (m4a/mp3/wav и т.д.)")
    parser.add_argument("--seg-mode", default="fixed", choices=["fixed", "vad", "diarize"], help="Стратегия разбиения перед ASR")
    parser.add_argument("--lang", default="ru", help="Язык для саммари")
    parser.add_argument("--format", dest="format", default="md", help="Формат саммари (md/json и т.п.)")
    parser.add_argument("--timeout", type=int, default=900, help="Ограничение по времени (сек.)")
    parser.add_argument("--poll", type=float, default=1.0, help="Период опроса статуса (сек.)")
    args = parser.parse_args()

    audio_path = _normalize_path(args.file)
    _print_header(args, audio_path)

    # 1) создаём транскрипт
    async with async_session() as s:
        tid = (await s.execute(insert(MfgTranscript).values(
            meeting_id=1,
            status="processing",
            filename=audio_path.name,
            file_path=str(audio_path),
        ).returning(MfgTranscript.id))).scalar_one()
        await s.commit()
    print(f"Created transcript_id={tid}")

    # 2) запускаем workflow как отдельную задачу
    task = asyncio.create_task(process_protokol(
        tid, str(audio_path), lang=args.lang, format_=args.format, seg_mode=args.seg_mode
    ))

    # 3) опрашиваем прогресс
    t0 = time.time()
    last_status = None
    last_step = None
    last_p = -1
    while True:
        job = await _fetch_job(tid)
        if job:
            if job.status != last_status or job.step != last_step or job.progress != last_p:
                _print_progress_line(job.status, job.progress, job.step)
                last_status, last_step, last_p = job.status, job.step, (job.progress or 0)

            if job.status in {"error", "done", "summary_done"}:
                break

        if task.done():
            break

        if time.time() - t0 > args.timeout:
            print("\n! Timeout reached, stopping polling (task may continue in background).")
            break

        await asyncio.sleep(args.poll)

    # гарантируем завершение задачи (получим исключение, если оно было)
    try:
        await asyncio.wait_for(task, timeout=5)
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        print("\n! Workflow raised exception:", repr(e))

    # 4) вывод сводки
    print("\n\n=== SUMMARY ===")
    job = await _fetch_job(tid)
    if job:
        print(f"final status = {job.status}")
        print(f"progress     = {job.progress}")
        print(f"step         = {job.step}")
        if job.error:
            print(f"error        = {job.error}")

    stats = await _counts(tid)
    for k, v in stats.items():
        print(f"{k:18s}: {v}")

    events = await _tail_events(tid, limit=20)
    if events:
        print("\nlast events:")
        for st, pr, step, ts in events:
            prtxt = "" if pr is None else f"{pr:3d}%"
            print(f"  {ts} | {st:<24} {prtxt:<5} {step or ''}")

    print("\nDone.\n")


if __name__ == "__main__":
    asyncio.run(main())
