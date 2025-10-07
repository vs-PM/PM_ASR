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


async def _load_diar_chunks(session: AsyncSession, transcript_id: int, mode: str | None = None) -> List[MfgDiarization]:
    """Загрузить чанки диаризации для транскрипции (с учётом режима)."""
    q = select(MfgDiarization).where(MfgDiarization.transcript_id == transcript_id)
    if mode is not None:
        q = q.where(MfgDiarization.mode == mode)
    rows = (await session.execute(q.order_by(MfgDiarization.start_ts))).scalars().all()
    return rows


async def _load_existing_segments(session: AsyncSession, transcript_id: int, mode: str | None) -> Dict[Tuple[float, float], int]:
    """
    Ключи уже сохранённых сегментов для заданного режима: (start, end) → 1.
    Нужен именно режим, чтобы не считать "дубликатами" сегменты других режимов.
    """
    q = (
        select(MfgSegment.start_ts, MfgSegment.end_ts)
        .where(MfgSegment.transcript_id == transcript_id)
    )
    if mode is not None:
        q = q.where(MfgSegment.mode == mode)
    rows = (await session.execute(q)).all()
    return {(float(s), float(e)): 1 for (s, e) in rows}


async def _persist_segments(
    session: AsyncSession,
    transcript_id: int,
    items: List[dict],
    mode: str | None,
) -> int:
    if not items:
        return 0

    the_mode = mode or "diarize"  # дефолт на случай отсутствия режима

    payload = [
        dict(
            transcript_id=transcript_id,
            start_ts=float(it["start_ts"]),
            end_ts=float(it["end_ts"]),
            text=str(it.get("text") or ""),
            speaker=it.get("speaker"),
            lang=(it.get("lang") or None),
            mode=the_mode,  # ← критично
        )
        for it in items
    ]

    insert_stmt = pg_insert(MfgSegment).values(payload)

    # ВАЖНО: имя констрейнта должно совпадать с миграцией с mode.
    # Если у тебя UC называется иначе — поменяй тут имя на фактическое.
    upsert_stmt = insert_stmt.on_conflict_do_update(
        constraint="uq_mfg_segment_range_mode",
        set_=dict(
            text=insert_stmt.excluded.text,
            speaker=insert_stmt.excluded.speaker,
            lang=insert_stmt.excluded.lang,
            mode=insert_stmt.excluded.mode,  # на случай, если захотим обновлять mode (обычно не нужно)
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


async def process_pipeline_segments(transcript_id: int, language: str = "ru", mode: str | None = None) -> dict:
    """
    Поток:
      1) берём чанки из mfg_diarization по mode,
      2) фильтруем уже записанные интервалы ТОЛЬКО для этого mode,
      3) транскрибируем каждый чанк,
      4) UPSERT в mfg_segment с mode,
      5) переводим транскрипт в transcription_done.
    """
    async with async_session() as session:
        diar_chunks = await _load_diar_chunks(session, transcript_id, mode=mode)
        if not diar_chunks:
            log.info("Нет чанков диаризации для tid=%s mode=%s — помечаю transcription_done", transcript_id, mode)
            await _mark_transcript_done(session, transcript_id)
            return {"found_chunks": 0, "existing_segments": 0, "new_segments": 0, "mode": mode}

        existing_map = await _load_existing_segments(session, transcript_id, mode)

        log.info("Найдено %d чанков для транскрипции (tid=%s, mode=%s)", len(diar_chunks), transcript_id, mode)
        log.debug("Уже существует сегментов (mode=%s): %d (tid=%s)", mode, len(existing_map), transcript_id)

        # Для удобства логирования группируем по файлу
        by_file: Dict[str, List[MfgDiarization]] = defaultdict(list)
        for c in diar_chunks:
            by_file[c.file_path].append(c)

        total_saved = 0

        for wav_path, group in by_file.items():
            # оставляем только новые интервалы для этого mode
            group = [
                c
                for c in group
                if (float(c.start_ts), float(c.end_ts)) not in existing_map
            ]
            if not group:
                log.info(
                    "Для файла %s все %d интервалов уже есть в mfg_segment (tid=%s, mode=%s)",
                    wav_path, len(by_file[wav_path]), transcript_id, mode
                )
                continue

            log.info(
                "К транскрипции новых сегментов: %d (tid=%s, file=%s, mode=%s)",
                len(group), transcript_id, wav_path, mode
            )

            to_save: List[dict] = []

            for c in group:
                start = float(c.start_ts)
                end = float(c.end_ts)

                if end - start <= 1e-6:
                    continue

                try:
                    txt = await _call_asr(wav_path, start, end, language=language)
                except Exception:
                    log.exception(
                        "ASR error on window [%s..%s] file=%s tid=%s mode=%s",
                        start, end, wav_path, transcript_id, mode
                    )
                    continue

                if not txt.strip():
                    continue

                chunk_lang = getattr(c, "lang", None) or language
                txt_len = len(txt)
                log.debug("ASR window ok: [%0.2f..%0.2f] → len=%d (tid=%s, mode=%s)", start, end, txt_len, transcript_id, mode)

                to_save.append(
                    dict(
                        start_ts=start,
                        end_ts=end,
                        text=txt,
                        speaker=c.speaker,
                        lang=chunk_lang,
                    )
                )

            log.debug("Persist %d segments via upsert (tid=%s, mode=%s)", len(to_save), transcript_id, mode)
            saved = await _persist_segments(session, transcript_id, to_save, mode)
            total_saved += saved
            log.info("Сохранено/обновлено сегментов: +%d (tid=%s, file=%s, mode=%s)", saved, transcript_id, wav_path, mode)

        await _mark_transcript_done(session, transcript_id)

        return {
            "found_chunks": len(diar_chunks),
            "existing_segments": len(existing_map),
            "new_segments": total_saved,
            "mode": mode,
        }
