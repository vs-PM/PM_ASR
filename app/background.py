from __future__ import annotations

import asyncio
from pathlib import Path
import torch

from app.services.asr_service import transcribe_file
from app.services.diarization_service import diarize_file
from app.services.embeddings_service import embed_text
from app.services.pipeline_service import process_pipeline_segments
from app.services.vad_service import segment_vad, segment_fixed
from app.services.summary.service import generate_protocol

from app.database import async_session
from app.models import MfgTranscript, MfgDiarization, MfgSegment, MfgEmbedding
from app.logger import get_logger

log = get_logger(__name__)

# ─────────────────────────────────────────
# Единственный запуск на transcript_id
# ─────────────────────────────────────────
_RUN_LOCKS: dict[int, asyncio.Lock] = {}

def _get_lock(tid: int) -> asyncio.Lock:
    lock = _RUN_LOCKS.get(tid)
    if lock is None:
        lock = asyncio.Lock()
        _RUN_LOCKS[tid] = lock
    return lock

# ─────────────────────────────────────────
# 1) Транскрипция целого файла (старый путь)
# ─────────────────────────────────────────
async def process_transcription(transcript_id: int, audio_path: str):
    log.info("Запуск фоновой транскрипции: tid=%s path=%s", transcript_id, audio_path)
    async with async_session() as session:
        transcript = await session.get(MfgTranscript, transcript_id)
        if not transcript:
            log.error("Transcript %s не найден", transcript_id)
            return

        try:
            text = await transcribe_file(audio_path)
            transcript.processed_text = text
            transcript.status = "transcription_done"
            session.add(transcript)
            await session.commit()
            log.info("Транскрипция завершена: tid=%s, len=%s", transcript_id, len(text))
        except Exception:
            transcript.status = "error"
            session.add(transcript)
            await session.commit()
            log.exception("Ошибка транскрипции: tid=%s", transcript_id)
        finally:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception:
                log.warning("Не удалось удалить временный файл: %s", audio_path)
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                log.debug("CUDA cache cleared after transcription")
            log.info("Фоновая задача транскрипции завершена: tid=%s", transcript_id)

# ─────────────────────────────────────────
# 2) Диаризация (pyannote)
# ─────────────────────────────────────────
async def process_diarization(transcript_id: int, audio_path: str):
    log.info("Диаризация старт: tid=%s file=%s", transcript_id, audio_path)
    async with async_session() as session:
        transcript = await session.get(MfgTranscript, transcript_id)
        if not transcript:
            log.error("Transcript %s не найден", transcript_id)
            return
        try:
            chunks = await diarize_file(audio_path)
            for c in chunks:
                session.add(MfgDiarization(
                    transcript_id=transcript_id,
                    speaker=c["speaker"],
                    start_ts=c["start_ts"],
                    end_ts=c["end_ts"],
                    file_path=c["file_path"],
                ))
            transcript.status = "diarization_done"
            session.add(transcript)
            await session.commit()
            log.info("Диаризация завершена: tid=%s chunks=%d", transcript_id, len(chunks))
        except Exception:
            transcript.status = "error"
            session.add(transcript)
            await session.commit()
            log.exception("Ошибка диаризации: tid=%s", transcript_id)
        finally:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception:
                log.warning("Не удалось удалить временный файл: %s", audio_path)
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                log.debug("CUDA cache cleared after diarization")
            log.info("Фон. задача диаризации завершена: tid=%s", transcript_id)

# ─────────────────────────────────────────
# 2a) Сегментация без диаризации (VAD / fixed)
# ─────────────────────────────────────────
async def process_segmentation(transcript_id: int, audio_path: str, mode: str = "vad"):
    log.info("Сегментация старт: tid=%s mode=%s", transcript_id, mode)
    async with async_session() as session:
        transcript = await session.get(MfgTranscript, transcript_id)
        if not transcript:
            log.error("Transcript %s не найден", transcript_id)
            return
        try:
            if mode == "vad":
                wav16k, chunks = await segment_vad(audio_path)
            else:
                wav16k, chunks = await segment_fixed(audio_path)
            for c in chunks:
                session.add(MfgDiarization(
                    transcript_id=transcript_id,
                    speaker=c["speaker"],
                    start_ts=c["start_ts"],
                    end_ts=c["end_ts"],
                    file_path=c["file_path"],
                ))
            transcript.status = "diarization_done"
            session.add(transcript)
            await session.commit()
            log.info("Сегментация завершена: tid=%s segments=%d (%s)", transcript_id, len(chunks), mode)
        except Exception:
            transcript.status = "error"
            session.add(transcript)
            await session.commit()
            log.exception("Сегментация упала: tid=%s", transcript_id)

# ─────────────────────────────────────────
# 3) Pipeline: транскрипция сегментов
# ─────────────────────────────────────────
async def process_pipeline(transcript_id: int):
    log.info("Pipeline старт: tid=%s", transcript_id)
    try:
        await process_pipeline_segments(transcript_id)
        log.info("Pipeline завершён: tid=%s", transcript_id)
    except Exception:
        async with async_session() as session:
            transcript = await session.get(MfgTranscript, transcript_id)
            if transcript:
                transcript.status = "error"
                session.add(transcript)
                await session.commit()
        log.exception("Pipeline ошибка: tid=%s", transcript_id)

# ─────────────────────────────────────────
# 4) Генерация эмбеддингов
# ─────────────────────────────────────────
async def process_embeddings(transcript_id: int):
    log.info("Embeddings старт: tid=%s", transcript_id)
    async with async_session() as session:
        transcript = await session.get(MfgTranscript, transcript_id)
        if not transcript:
            log.error("Transcript %s не найден", transcript_id)
            return
        try:
            segments_res = await session.execute(
                MfgSegment.__table__.select().where(MfgSegment.transcript_id == transcript_id)
            )
            segments = segments_res.fetchall()
            log.info("Сегментов для эмбеддингов: %d (tid=%s)", len(segments), transcript_id)

            for seg in segments:
                emb = await embed_text(seg.text)
                if emb:
                    session.add(MfgEmbedding(segment_id=seg.id, embedding=emb))
            transcript.status = "embeddings_done"
            session.add(transcript)
            await session.commit()
            log.info("Embeddings завершены: tid=%s", transcript_id)
        except Exception:
            transcript.status = "error"
            session.add(transcript)
            await session.commit()
            log.exception("Embeddings ошибка: tid=%s", transcript_id)

# ─────────────────────────────────────────
# 5) Итоговая суммаризация
# ─────────────────────────────────────────
async def process_summary(transcript_id: int, lang: str = "ru", format_: str = "md"):
    log.info("Суммаризация старт: tid=%s", transcript_id)
    # статус: начало
    async with async_session() as session:
        tr = await session.get(MfgTranscript, transcript_id)
        if not tr:
            log.error("Transcript not found tid=%s", transcript_id)
            return
        tr.status = "summary_processing"
        session.add(tr)
        await session.commit()

    try:
        await generate_protocol(transcript_id, lang=lang, output_format=format_)

        # статус: успех
        async with async_session() as session:
            tr = await session.get(MfgTranscript, transcript_id)
            if tr:
                tr.status = "summary_done"
                session.add(tr)
                await session.commit()
        log.info("Суммаризация завершена: tid=%s", transcript_id)

    except Exception:
        # статус: ошибка
        async with async_session() as session:
            tr = await session.get(MfgTranscript, transcript_id)
            if tr:
                tr.status = "error"
                session.add(tr)
                await session.commit()
        log.exception("Суммаризация ошибка: tid=%s", transcript_id)

# ─────────────────────────────────────────
# 6) Комбинированный протокол (анти-loop, state machine)
# ─────────────────────────────────────────
_DONE_STATES = {"summary_done", "done"}
_ERROR_STATES = {"error"}

async def process_protokol(
    transcript_id: int,
    audio_path: str,
    lang: str = "ru",
    format_: str = "json",
    seg_mode: str = "diarize",   # diarize | vad | fixed
):
    lock = _get_lock(transcript_id)
    if lock.locked():
        log.warning("Protokol уже выполняется: tid=%s — пропускаем повторный запуск", transcript_id)
        return

    async with lock:
        log.info("Protokol старт: tid=%s file=%s seg_mode=%s", transcript_id, audio_path, seg_mode)

        async with async_session() as session:
            transcript = await session.get(MfgTranscript, transcript_id)
            if not transcript:
                log.error("Transcript %s не найден", transcript_id)
                return

            # если уже всё сделано — выходим
            if transcript.status in _DONE_STATES:
                log.info("tid=%s уже завершён статусом %s — выходим", transcript_id, transcript.status)
                return
            if transcript.status in _ERROR_STATES:
                log.warning("tid=%s в состоянии error — выходим", transcript_id)
                return

        # 1) Диаризация/сегментация
        async with async_session() as session:
            transcript = await session.get(MfgTranscript, transcript_id)
            if transcript.status not in {"diarization_done", "transcription_done", "embeddings_done"}:
                transcript.status = "diarization_processing"
                session.add(transcript)
                await session.commit()

                if seg_mode == "diarize":
                    await process_diarization(transcript_id, audio_path)
                elif seg_mode in ("vad", "fixed"):
                    await process_segmentation(transcript_id, audio_path, mode=seg_mode)
                else:
                    log.error("Неизвестный seg_mode=%s, используя 'vad'", seg_mode)
                    await process_segmentation(transcript_id, audio_path, mode="vad")

        # 2) ASR по сегментам
        async with async_session() as session:
            transcript = await session.get(MfgTranscript, transcript_id)
            if transcript.status not in {"transcription_done", "embeddings_done"}:
                transcript.status = "pipeline_processing"
                session.add(transcript)
                await session.commit()
                await process_pipeline(transcript_id)

        # 3) Эмбеддинги
        async with async_session() as session:
            transcript = await session.get(MfgTranscript, transcript_id)
            if transcript.status != "embeddings_done":
                transcript.status = "embeddings_processing"
                session.add(transcript)
                await session.commit()
                await process_embeddings(transcript_id)

        # 4) Суммаризация
        async with async_session() as session:
            transcript = await session.get(MfgTranscript, transcript_id)
            if transcript.status not in _DONE_STATES:
                transcript.status = "summary_processing"
                session.add(transcript)
                await session.commit()
                await process_summary(transcript_id, lang=lang, format_=format_)

        log.info("Protokol завершён: tid=%s", transcript_id)
