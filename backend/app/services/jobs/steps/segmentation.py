from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgDiarization
from app.services.pipeline.vad import segment_vad, segment_fixed
from app.services.pipeline.media import convert_to_wav16k_mono

import wave
import contextlib
from pathlib import Path

log = get_logger(__name__)

def _wav_duration(path: str) -> float:
    """Вернуть длительность WAV-файла (сек) через стандартную библиотеку."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"WAV not found: {path}")
    with contextlib.closing(wave.open(str(p), "rb")) as wf:
        frames = wf.getnframes()
        rate = wf.getframerate() or 16000
        return frames / float(rate)

async def run(transcript_id: int, audio_path: str, mode: str = "vad") -> int:
    """
    Режимы:
      - vad   → webrtcvad
      - fixed → равные окна
      - full  → один чанк на весь файл
    """
    if mode == "vad":
        wav16k, chunks = await segment_vad(audio_path)

    elif mode == "fixed":
        wav16k, chunks = await segment_fixed(audio_path)

    elif mode == "full":
        # 1) конвертируем исходник в WAV 16k mono
        wav16k = await convert_to_wav16k_mono(audio_path)
        # 2) считаем длительность получившегося WAV без ffprobe
        dur = _wav_duration(wav16k)
        # 3) один чанк на весь файл
        chunks = [dict(speaker=None, start_ts=0.0, end_ts=float(dur))]

    else:
        raise RuntimeError(f"Unknown segmentation mode: {mode}")

    async with async_session() as s:
        for c in chunks:
            s.add(MfgDiarization(
                transcript_id=transcript_id,
                speaker=c.get("speaker"),
                start_ts=float(c["start_ts"]),
                end_ts=float(c["end_ts"]),
                file_path=wav16k,
                mode=mode,  # критично для выбора набора сегментов
            ))
        await s.commit()

    log.info("Segmentation(%s): saved %d chunks for tid=%s", mode, len(chunks), transcript_id)
    return len(chunks)
