# asr.py — ФИКС ОКОН
import math
from pathlib import Path
from typing import Optional, Iterable

import numpy as np
import torch
import torchaudio
from faster_whisper import WhisperModel

from app.core.logger import get_logger

log = get_logger(__name__)

MODEL_NAME = "large-v3"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"

log.info("Инициализация Whisper: model=%s device=%s compute_type=%s",
         MODEL_NAME, DEVICE, COMPUTE_TYPE)

try:
    whisper = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
    if DEVICE == "cuda":
        _ = torch.randn(1, device="cuda")
    log.info("Whisper успешно загружена")
except Exception:
    log.exception("Ошибка при инициализации Whisper")
    raise


def _transcribe(
    audio_source,
    language: str = "ru",
    beam_size: int = 2,
    vad_filter: bool = False,
    condition_on_previous_text: bool = False,
) -> str:
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
    out = "".join(text)
    log.debug("ASR done: segments=%d, total_len=%d", count, len(out))
    return out


async def transcribe_file(audio_path: str) -> str:
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


def _load_window_as_numpy(wav_path: str, start_ts: float, end_ts: float) -> np.ndarray:
    """
    Загружаем WAV и вырезаем окно [start_ts, end_ts] → np.float32 mono 16k.
    ВАЖНО: всегда режем ОКНО в обеих ветках dtype.
    """
    wav, sr = torchaudio.load(wav_path)  # wav: [C, T], обычно float32 в диапазоне [-1, 1]
    s = max(0, int(round(start_ts * sr)))
    e = min(wav.shape[-1], int(round(end_ts * sr)))
    if e <= s:
        return np.zeros((0,), dtype=np.float32)

    # Моно
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)

    # РЕЖЕМ окно в любом случае
    clip = wav[:, s:e].squeeze(0)

    # Приводим к float32
    if clip.dtype != torch.float32:
        clip = clip.to(torch.float32)

    # Если вдруг torchaudio вернул int16 (редко, при особых настройках) — нормализуем
    if wav.dtype == torch.int16:
        clip = clip / 32768.0

    return clip.cpu().numpy()


async def transcribe_window_from_wav(
    wav_path: str, start_ts: float, end_ts: float, language: str = "ru"
) -> str:
    try:
        audio_np = _load_window_as_numpy(wav_path, start_ts, end_ts)
        if audio_np.size == 0:
            return ""
        return _transcribe(audio_np, language=language) or ""
    except Exception:
        log.exception("Ошибка транскрипции окна: %s [%.2f, %.2f]", wav_path, start_ts, end_ts)
        return ""
