from __future__ import annotations

import math
from pathlib import Path
from typing import Optional, Iterable

import numpy as np
import torch
import torchaudio
from faster_whisper import WhisperModel

from app.core.logger import get_logger

log = get_logger(__name__)

# ── Настройки модели (можно вынести в config при желании)
MODEL_NAME = "large-v3"

# Определяем устройство и compute_type корректно
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
if DEVICE == "cuda":
    COMPUTE_TYPE = "float16"           # быстрее и экономит VRAM
else:
    COMPUTE_TYPE = "int8"              # для CPU; можно "float32" если важнее качество

log.info("Инициализация Whisper: model=%s device=%s compute_type=%s",
         MODEL_NAME, DEVICE, COMPUTE_TYPE)

try:
    whisper = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
    if DEVICE == "cuda":
        _ = torch.randn(1, device="cuda")  # лёгкий прогрев CUDA
    log.info("Whisper успешно загружена")
except Exception:
    log.exception("Ошибка при инициализации Whisper")
    raise


def _transcribe(
    audio_source,                      # путь либо np.ndarray (float32, 16k), либо генератор
    language: str = "ru",
    beam_size: int = 2,               # окна маленькие -> 1-2 обычно достаточно
    vad_filter: bool = False,         # VAD уже был на этапе сегментации
    condition_on_previous_text: bool = False,
) -> str:
    """
    Общая обёртка: возвращает склеенный текст.
    """
    segments, _info = whisper.transcribe(
        audio_source,
        language=language,
        beam_size=beam_size,
        vad_filter=vad_filter,
        vad_parameters=dict(min_silence_duration_ms=500),
        condition_on_previous_text=condition_on_previous_text,
        task="transcribe",
    )
    text = []
    count = 0
    for seg in segments:
        count += 1
        text.append(seg.text)
        log.debug("ASR seg #%d: len=%d", count, len(seg.text))
    out = "".join(text)
    log.debug("ASR done: segments=%d, total_len=%d", count, len(out))
    return out


async def transcribe_file(audio_path: str) -> str:
    """
    Совместимость с текущим пайплайном: транскрибирует целый файл (или окно, если файл короткий).
    Используется как fallback в pipeline_service.
    """
    log.info("Транскрипция файла: %s", audio_path)
    if not Path(audio_path).exists():
        log.error("Файл не найден: %s", audio_path)
        raise FileNotFoundError(audio_path)
    try:
        text = _transcribe(str(audio_path))
        log.info("Транскрипция завершена: file=%s, len=%d", audio_path, len(text))
        return text
    except Exception:
        log.exception("Ошибка транскрипции файла: %s", audio_path)
        raise


# ── Опционально: прямые методы для окон без временных файлов ───────────────────

def _load_window_as_numpy(
    wav_path: str, start_ts: float, end_ts: float
) -> np.ndarray:
    """
    Загружаем WAV и вырезаем окно [start_ts, end_ts] → np.float32 mono 16k для faster-whisper.
    """
    wav, sr = torchaudio.load(wav_path)  # [C, T]
    s = max(0, int(math.floor(start_ts * sr)))
    e = min(wav.shape[-1], int(math.ceil(end_ts * sr)))
    if e <= s:
        return np.zeros((0,), dtype=np.float32)
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)  # моно
    clip = wav[:, s:e].squeeze(0).to(torch.float32) / 32768.0 if wav.dtype == torch.int16 else wav.squeeze(0).to(torch.float32)
    # faster-whisper ожидает float32 PCM -1..1 и sr=16k (если у тебя всегда 16k, ок)
    return clip.cpu().numpy()


async def transcribe_window_from_wav(
    wav_path: str, start_ts: float, end_ts: float, language: str = "ru"
) -> str:
    """
    Быстрая транскрипция окна без записи временного файла.
    Можно интегрировать в pipeline_service для ускорения.
    """
    try:
        audio_np = _load_window_as_numpy(wav_path, start_ts, end_ts)
        if audio_np.size == 0:
            return ""
        return _transcribe(audio_np, language=language)
    except Exception:
        log.exception("Ошибка транскрипции окна: %s [%.2f, %.2f]", wav_path, start_ts, end_ts)
        raise
