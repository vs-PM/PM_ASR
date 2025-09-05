# app/services/vad_service.py
from __future__ import annotations
import asyncio
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import webrtcvad  # pip install webrtcvad

from app.logger import get_logger
from app.config import settings
from app.services.ffmpeg_utils import convert_to_wav16k_mono

log = get_logger(__name__)

@dataclass
class SpeechSeg:
    start_ts: float
    end_ts: float

def _read_pcm16_mono_16k(path: str) -> tuple[bytes, int]:
    """Считываем WAV 16k mono PCM16 → байты и sample_rate."""
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        if sr != 16000 or ch != 1 or sampwidth != 2:
            raise RuntimeError(f"WAV must be 16k/mono/16-bit, got sr={sr}, ch={ch}, w={sampwidth}")
        pcm = wf.readframes(wf.getnframes())
    return pcm, sr

def _frame_generator(pcm: bytes, sr: int, frame_ms: int) -> List[bytes]:
    """Режем на короткие фреймы (10/20/30 ms) для webrtcvad."""
    bytes_per_sample = 2  # 16-bit
    frame_size = int(sr * frame_ms / 1000) * bytes_per_sample
    return [pcm[i:i+frame_size] for i in range(0, len(pcm), frame_size) if i+frame_size <= len(pcm)]

def _collect_speech_regions(
    frames: List[bytes],
    sr: int,
    frame_ms: int,
    aggressiveness: int,
    min_speech_ms: int,
    min_silence_ms: int,
) -> List[SpeechSeg]:
    vad = webrtcvad.Vad(aggressiveness)
    segs: List[SpeechSeg] = []
    in_speech = False
    seg_start: Optional[float] = None
    silence_acc = 0
    for i, fr in enumerate(frames):
        ts = i * (frame_ms / 1000.0)
        is_speech = vad.is_speech(fr, sr)
        if is_speech:
            if not in_speech:
                in_speech = True
                seg_start = ts
            silence_acc = 0
        else:
            if in_speech:
                silence_acc += frame_ms
                if silence_acc >= min_silence_ms:
                    # закрываем сегмент
                    end_ts = ts
                    if seg_start is not None and (end_ts - seg_start) * 1000 >= min_speech_ms:
                        segs.append(SpeechSeg(seg_start, end_ts))
                    in_speech, seg_start, silence_acc = False, None, 0
    # хвост
    if in_speech and seg_start is not None:
        end_ts = len(frames) * (frame_ms / 1000.0)
        if (end_ts - seg_start) * 1000 >= min_speech_ms:
            segs.append(SpeechSeg(seg_start, end_ts))
    return segs

def _merge_and_chunk(
    segs: List[SpeechSeg],
    max_gap_sec: float,
    max_len_sec: float,
    overlap_sec: float,
) -> List[SpeechSeg]:
    """Склеиваем близкие сегменты и режем длинные в окна с overlap."""
    if not segs:
        return []
    # merge by gap
    merged: List[SpeechSeg] = [segs[0]]
    for s in segs[1:]:
        last = merged[-1]
        if s.start_ts - last.end_ts <= max_gap_sec:
            merged[-1] = SpeechSeg(last.start_ts, max(s.end_ts, last.end_ts))
        else:
            merged.append(s)
    # cut long ones
    out: List[SpeechSeg] = []
    for s in merged:
        cur = s.start_ts
        while cur < s.end_ts:
            end = min(cur + max_len_sec, s.end_ts)
            out.append(SpeechSeg(cur, end))
            if end >= s.end_ts:
                break
            cur = end - overlap_sec  # шаг с overlap
    return out

async def segment_vad(audio_path: str) -> tuple[str, List[dict]]:
    """
    Возвращает (wav16k_path, список сегментов) без спикеров:
    [{"speaker":"SPEECH","start_ts":...,"end_ts":...,"file_path":wav16k_path}, ...]
    """
    # 1) конверт (пропускаем, если уже wav16k mono)
    wav16k = await convert_to_wav16k_mono(audio_path, threads=settings.ffmpeg_threads)
    pcm, sr = _read_pcm16_mono_16k(wav16k)

    frame_ms = int(getattr(settings, "vad_frame_ms", 20))
    aggr = int(getattr(settings, "vad_aggressiveness", 2))  # 0–3
    min_speech_ms = int(getattr(settings, "vad_min_speech_ms", 250))
    min_silence_ms = int(getattr(settings, "vad_min_silence_ms", 300))
    max_gap_sec = float(getattr(settings, "vad_merge_max_gap_sec", 0.3))
    max_len_sec = float(getattr(settings, "vad_max_segment_sec", 30))
    overlap_sec = float(getattr(settings, "seg_overlap_sec", 2.0))

    t0 = time.monotonic()
    frames = _frame_generator(pcm, sr, frame_ms)
    raw = _collect_speech_regions(frames, sr, frame_ms, aggr, min_speech_ms, min_silence_ms)
    segs = _merge_and_chunk(raw, max_gap_sec, max_len_sec, overlap_sec)
    elapsed = time.monotonic() - t0
    dur = len(pcm) / (sr * 2)  # bytes → samples → seconds

    log.info(
        "VAD: found %d raw, %d merged/chunked in %.2fs for %.2fs audio (RTF=%.3f)",
        len(raw), len(segs), elapsed, dur, elapsed / dur if dur > 0 else 0.0
    )

    chunks = [{
        "speaker": "SPEECH",
        "start_ts": float(s.start_ts),
        "end_ts": float(s.end_ts),
        "file_path": wav16k
    } for s in segs]
    return wav16k, chunks

async def segment_fixed(audio_path: str) -> tuple[str, List[dict]]:
    """
    Простая нарезка на окна фиксированной длины, например 30с, с overlap.
    """
    wav16k = await convert_to_wav16k_mono(audio_path, threads=settings.ffmpeg_threads)

    import torchaudio
    info = torchaudio.info(wav16k)
    sr = info.sample_rate
    total_sec = info.num_frames / sr
    win = float(getattr(settings, "fixed_window_sec", 30))
    ovl = float(getattr(settings, "fixed_overlap_sec", 5))

    segs: List[SpeechSeg] = []
    cur = 0.0
    while cur < total_sec:
        end = min(cur + win, total_sec)
        segs.append(SpeechSeg(cur, end))
        if end >= total_sec:
            break
        cur = end - ovl

    chunks = [{
        "speaker": "SPEECH",
        "start_ts": float(s.start_ts),
        "end_ts": float(s.end_ts),
        "file_path": wav16k
    } for s in segs]

    log.info("FIXED: %d segments (win=%.1fs, ovl=%.1fs) for %.1fs audio",
             len(chunks), win, ovl, total_sec)
    return wav16k, chunks
