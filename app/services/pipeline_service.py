# app/services/pipeline_service.py
from __future__ import annotations

import math
from collections import defaultdict
from typing import List, Dict, Tuple

import torchaudio
import torch

from sqlalchemy import select
from app.services.asr_service import transcribe_file  # будем вызывать на временном файле как fallback
from app.database import async_session
from app.models import MfgDiarization, MfgSegment, MfgTranscript
from app.logger import get_logger
import tempfile
from pathlib import Path

log = get_logger(__name__)


async def _transcribe_window_from_wav(
    wav_path: str, start_ts: float, end_ts: float
) -> str:
    """
    Быстрый транскрипт тайм-окна [start_ts, end_ts] из общего WAV.
    Пытаемся не создавать файлов. Если у твоего ASR уже есть функция работы с тензором —
    используй её тут. Пока делаем через временный WAV для совместимости.
    """
    # Загружаем и режем по сэмплам
    wav, sr = torchaudio.load(wav_path)  # [channels, samples]
    s = max(0, int(math.floor(start_ts * sr)))
    e = min(wav.shape[-1], int(math.ceil(end_ts * sr)))
    if e <= s:
        return ""

    clip = wav[:, s:e]

    # Если у тебя есть прямой вызов по тензору (без файла), замени блок ниже на него:
    # text = await transcribe_tensor(clip, sr)
    # return text

    # Fallback: пишем во временный файл и используем существующий transcribe_file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpf:
        tmp_path = tmpf.name
    try:
        torchaudio.save(tmp_path, clip, sr)
        text = await transcribe_file(tmp_path)
        return text or ""
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            log.warning("Не удалось удалить временный файл сегмента: %s", tmp_path)


async def process_pipeline_segments(transcript_id: int):
    """
    Идемпотентная транскрипция:
      - читаем все чанки из MfgDiarization для данного transcript_id
      - пропускаем те, для которых сегмент уже существует (точное совпадение speaker/start/end)
      - для остальных режем окно из общего WAV по таймкодам и транскрибируем только это окно
    В конце выставляем status='transcription_done'.
    """
    async with async_session() as session:
        # 1) Читаем чанки диаризации
        diar_q = select(MfgDiarization).where(MfgDiarization.transcript_id == transcript_id).order_by(MfgDiarization.start_ts)
        diar_rows = (await session.execute(diar_q)).scalars().all()
        if not diar_rows:
            log.warning("Нет чанков диаризации для transcript_id=%s — нечего транскрибировать", transcript_id)
            # Даже если нечего делать, считаем шаг завершённым, чтобы процесс не циклился
            tr = await session.get(MfgTranscript, transcript_id)
            if tr:
                tr.status = "transcription_done"
                session.add(tr)
                await session.commit()
            return

        log.info("Найдено %d чанков для транскрипции (tid=%s)", len(diar_rows), transcript_id)

        # 2) Собираем уже существующие сегменты, чтобы не дублировать
        seg_q = select(MfgSegment.speaker, MfgSegment.start_ts, MfgSegment.end_ts).where(
            MfgSegment.transcript_id == transcript_id
        )
        existing = set((spk, float(st), float(en)) for spk, st, en in (await session.execute(seg_q)).all())
        log.debug("Уже существует сегментов: %d (tid=%s)", len(existing), transcript_id)

        # 3) Группируем чанки по wav-файлу (в VAD/fixed у всех один путь)
        groups: Dict[str, List[MfgDiarization]] = defaultdict(list)
        for d in diar_rows:
            key = (d.speaker, float(d.start_ts), float(d.end_ts))
            if key in existing:
                continue  # уже есть — пропускаем
            groups[d.file_path].append(d)

        total_new = sum(len(v) for v in groups.values())
        if total_new == 0:
            log.info("Новых сегментов нет, пропускаем транскрипцию (tid=%s)", transcript_id)
            tr = await session.get(MfgTranscript, transcript_id)
            if tr:
                tr.status = "transcription_done"
                session.add(tr)
                await session.commit()
            return

        log.info("К транскрипции новых сегментов: %d (tid=%s, файлов=%d)", total_new, transcript_id, len(groups))

        # 4) По каждому wav режем окна и транскрибируем
        created = 0
        for wav_path, segs in groups.items():
            # Опционально: можно один раз загрузить аудио и резать тензор,
            # но мы уже делаем это внутри _transcribe_window_from_wav по необходимости.
            for d in segs:
                text = await _transcribe_window_from_wav(wav_path, float(d.start_ts), float(d.end_ts))
                segment = MfgSegment(
                    transcript_id=transcript_id,
                    speaker=d.speaker,
                    start_ts=float(d.start_ts),
                    end_ts=float(d.end_ts),
                    text=text or "",
                )
                session.add(segment)
                created += 1

            # коммитим батчами
            await session.commit()
            log.debug("Добавлено сегментов: +%d (tid=%s, файл=%s)", len(segs), transcript_id, wav_path)

        # 5) финальный статус
        tr = await session.get(MfgTranscript, transcript_id)
        if tr:
            tr.status = "transcription_done"
            session.add(tr)
            await session.commit()
        log.info("Транскрипция завершена: tid=%s, добавлено сегментов=%d", transcript_id, created)
