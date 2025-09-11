from __future__ import annotations

import inspect

from collections import defaultdict
from typing import List, Dict, Tuple

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.db.models import MfgDiarization, MfgSegment, MfgTranscript
from app.core.logger import get_logger
from app.services.pipeline.asr import transcribe_window_from_wav

log = get_logger(__name__)

_IS_ASYNC_ASR = inspect.iscoroutinefunction(transcribe_window_from_wav)

async def _load_diar_chunks(session: AsyncSession, transcript_id: int) -> List[MfgDiarization]:
    """Загрузить чанки диаризации для транскрипции."""
    rows = (
        await session.execute(
            select(MfgDiarization)
            .where(MfgDiarization.transcript_id == transcript_id)
            .order_by(MfgDiarization.start_ts)
        )
    ).scalars().all()
    return rows


async def _load_existing_segments(session: AsyncSession, transcript_id: int) -> Dict[Tuple[float, float], int]:
    """Ключи уже сохранённых сегментов (tid, start, end), чтобы не дублировать UPSERT-ом лишнее."""
    rows = (
        await session.execute(
            select(MfgSegment.start_ts, MfgSegment.end_ts)
            .where(MfgSegment.transcript_id == transcript_id)
        )
    ).all()
    return {(float(s), float(e)): 1 for (s, e) in rows}

async def _persist_segments(
    session: AsyncSession,
    transcript_id: int,
    items: List[dict],
) -> int:
    if not items:
        return 0

    payload = [
        dict(
            transcript_id=transcript_id,
            start_ts=float(it["start_ts"]),
            end_ts=float(it["end_ts"]),
            text=str(it.get("text") or ""),
            speaker=it.get("speaker"),
            lang=(it.get("lang") or None),
            # updated_at не пишем — сработает server_default
        )
        for it in items
    ]

    insert_stmt = pg_insert(MfgSegment).values(payload)

    upsert_stmt = insert_stmt.on_conflict_do_update(
        # можно и через индекс-колонки, но у тебя есть именованный уникальный констрейнт:
        constraint="uq_mfg_segments_tid_range",
        set_=dict(
            text=insert_stmt.excluded.text,
            speaker=insert_stmt.excluded.speaker,
            lang=insert_stmt.excluded.lang,
            # важно: на апдейте обновим таймстамп явно
            updated_at=func.now(),
        ),
    )

    await session.execute(upsert_stmt)
    await session.commit()
    return len(items)



async def _mark_transcript_done(session: AsyncSession, transcript_id: int) -> None:
    """Пометить транскрипт завершённым по шагу transcription."""
    tr = await session.get(MfgTranscript, transcript_id)
    if not tr:
        raise RuntimeError(f"Transcript {transcript_id} not found")
    tr.status = "transcription_done"
    session.add(tr)
    await session.commit()

async def _call_asr(wav_path: str, start: float, end: float, language: str) -> str:
    """
    Унифицированный вызов ASR: если функция async — ждём, если sync — вызываем напрямую.
    Возвращаем строку (пустую, если ничего не распознано).
    """
    if _IS_ASYNC_ASR:
        txt = await transcribe_window_from_wav(wav_path, start, end, language=language)
    else:
        txt = transcribe_window_from_wav(wav_path, start, end, language=language)

    if txt is None:
        return ""

    if isinstance(txt, str):
        return txt

    # Фоллбэк: если вернулась структура, пробуем извлечь текст
    if isinstance(txt, dict):
        return txt.get("text", "") or ""
    if isinstance(txt, (list, tuple)) and txt and isinstance(txt[0], str):
        return txt[0]

    return ""

async def process_pipeline_segments(transcript_id: int, language: str = "ru") -> dict:
    """
    Надёжный поток:
      1) берём чанки из mfg_diarization,
      2) фильтруем уже записанные интервалы,
      3) транскрибируем КАЖДЫЙ чанк по окну (start..end),
      4) UPSERT в mfg_segment (включая lang и updated_at) + commit,
      5) переводим транскрипт в transcription_done.
    """
    async with async_session() as session:
        diar_chunks = await _load_diar_chunks(session, transcript_id)
        if not diar_chunks:
            log.info("Нет чанков диаризации для tid=%s — помечаю transcription_done", transcript_id)
            await _mark_transcript_done(session, transcript_id)
            return {"found_chunks": 0, "existing_segments": 0, "new_segments": 0}

        existing_map = await _load_existing_segments(session, transcript_id)

        log.info("Найдено %d чанков для транскрипции (tid=%s)", len(diar_chunks), transcript_id)
        log.debug("Уже существует сегментов: %d (tid=%s)", len(existing_map), transcript_id)

        # Для удобства логирования группируем по файлу
        by_file: Dict[str, List[MfgDiarization]] = defaultdict(list)
        for c in diar_chunks:
            by_file[c.file_path].append(c)

        total_saved = 0

        for wav_path, group in by_file.items():
            # оставляем только новые интервалы
            group = [
                c
                for c in group
                if (float(c.start_ts), float(c.end_ts)) not in existing_map
            ]
            if not group:
                log.info(
                    "Для файла %s все %d интервалов уже есть в mfg_segment (tid=%s)",
                    wav_path, len(by_file[wav_path]), transcript_id
                )
                continue

            log.info(
                "К транскрипции новых сегментов: %d (tid=%s, файлов=1, file=%s)",
                len(group), transcript_id, wav_path
            )

            to_save: List[dict] = []

            # Транскрибируем каждый чанк отдельно (устойчиво и прозрачно по логам)
            for c in group:
                start = float(c.start_ts)
                end = float(c.end_ts)

                # Гарантируем положительную длительность окна
                if end - start <= 1e-6:
                    continue

                try:
                    txt = await _call_asr(wav_path, start, end, language=language)
                except Exception:
                    log.exception(
                        "ASR error on window [%s..%s] file=%s tid=%s",
                        start, end, wav_path, transcript_id
                    )
                    # пропускаем только конкретный чанк, пайплайн продолжается
                    continue

                if not txt.strip():
                    continue

                # Если у чанка есть свой lang — используем его, иначе общий language
                chunk_lang = getattr(c, "lang", None) or language
                txt_len = len(txt)
                log.debug("ASR window ok: [%0.2f..%0.2f] → len=%d (tid=%s)", start, end, txt_len, transcript_id)

                to_save.append(
                    dict(
                        start_ts=start,
                        end_ts=end,
                        text=txt,
                        speaker=c.speaker,
                        lang=chunk_lang,
                    )
                )

            log.debug("Persist %d segments via upsert (tid=%s)", len(to_save), transcript_id)
            saved = await _persist_segments(session, transcript_id, to_save)
            total_saved += saved
            log.info("Сохранено/обновлено сегментов: +%d (tid=%s, файл=%s)", saved, transcript_id, wav_path)

        # финальный статус шага
        await _mark_transcript_done(session, transcript_id)

        return {
            "found_chunks": len(diar_chunks),
            "existing_segments": len(existing_map),
            "new_segments": total_saved,
        }
