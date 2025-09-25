from __future__ import annotations

import asyncio
import time
import warnings
from pathlib import Path
from threading import Lock
from typing import List, Dict

import torch
from pyannote.audio import Pipeline
from pyannote.audio.pipelines import SpeakerDiarization
from pyannote.audio.utils.reproducibility import ReproducibilityWarning

from app.core.config import settings
from app.core.logger import get_logger
from app.services.pipeline.media import convert_to_wav16k_mono

log = get_logger(__name__)
warnings.filterwarnings("ignore", category=ReproducibilityWarning)

MODEL_NAME = "pyannote/speaker-diarization-3.1"

# ─────────────────────────────────────────
# Lazy singleton pipeline
# ─────────────────────────────────────────
_pipeline: SpeakerDiarization | None = None
_pipeline_lock = Lock()

def _load_pipeline_sync() -> SpeakerDiarization:
    token = settings.hf_token
    if not token:
        raise RuntimeError("HF token is empty. Set HF_TOKEN in .env")
    device = torch.device(settings.device if torch.cuda.is_available() and settings.device.startswith("cuda") else "cpu")
    pipe = Pipeline.from_pretrained(MODEL_NAME, use_auth_token=token)
    pipe.to(device)
    log.info("Pyannote pipeline loaded on %s", device)
    return pipe

def get_pipeline() -> SpeakerDiarization:
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = _load_pipeline_sync()
    return _pipeline

# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────
def _merge_chunks(chunks: List[Dict], min_len: float = 1.0, max_gap: float = 0.3) -> List[Dict]:
    """
    Склеиваем подряд идущие сегменты одного спикера с небольшой паузой между ними
    и прилипляем слишком короткие огрызки (< min_len) к предыдущему сегменту.
    """
    if not chunks:
        return []
    merged: List[Dict] = [dict(chunks[0])]
    for c in chunks[1:]:
        last = merged[-1]
        if c["speaker"] == last["speaker"] and (c["start_ts"] - last["end_ts"]) <= max_gap:
            last["end_ts"] = c["end_ts"]
        else:
            merged.append(dict(c))

    out: List[Dict] = []
    for m in merged:
        dur = m["end_ts"] - m["start_ts"]
        if dur >= min_len or not out:
            out.append(m)
        else:
            # коротыш -> прилипляем хвостом к предыдущему
            out[-1]["end_ts"] = m["end_ts"]
    return out

# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
async def diarize_file(audio_path: str) -> List[Dict]:
    """
    Диаризация; возвращает список сегментов:
    [{"speaker": "SPEAKER_00", "start_ts": float, "end_ts": float, "file_path": "<wav16k mono>"}]
    В file_path кладём единый WAV 16k mono (без нарезки на диск).
    """
    # 1) быстрый конверт/нормализация формата
    wav16k_path = await convert_to_wav16k_mono(audio_path, threads=0)  # 0 = пусть ffmpeg сам решит
    log.debug("Using WAV for diarization: %s", wav16k_path)

    # 2) лениво получаем пайплайн и считаем
    loop = asyncio.get_running_loop()
    pipeline = await loop.run_in_executor(None, get_pipeline)

    t0 = time.time()
    # В 3.x корректный вызов — словарь с ключом "audio" (можно и путь, но так надёжнее)
    diarization = await loop.run_in_executor(None, lambda: pipeline({"audio": wav16k_path}))
    elapsed = time.time() - t0
    log.info("pyannote diarization done in %.2fs for %s", elapsed, wav16k_path)

    # 3) собираем сегменты (без записи чанков на диск)
    chunks: List[Dict] = []
    for idx, (turn, _, speaker) in enumerate(diarization.itertracks(yield_label=True)):
        chunks.append({
            "speaker": speaker,
            "start_ts": float(turn.start),
            "end_ts": float(turn.end),
            "file_path": str(wav16k_path),
        })

    # 4) пост-обработка (склейка)
    before = len(chunks)
    chunks = _merge_chunks(chunks, min_len=1.0, max_gap=0.3)
    log.info("Diarization produced %d -> %d segments (merged) for %s", before, len(chunks), audio_path)

    return chunks
