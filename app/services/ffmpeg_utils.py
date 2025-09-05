from __future__ import annotations
import asyncio
import json
import shlex
import time
from pathlib import Path
from typing import Optional, Tuple
from app.logger import get_logger

log = get_logger(__name__)

async def probe_audio(path: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """
    Вернёт (codec_name, channels, sample_rate) первой аудиодорожки, либо (None, None, None) при ошибке.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,channels,sample_rate",
        "-of", "json", path
    ]
    try:
        t0 = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            log.warning("ffprobe failed rc=%s err=%s", proc.returncode, err.decode("utf-8", "ignore"))
            return None, None, None
        data = json.loads(out.decode("utf-8"))
        stream = (data.get("streams") or [None])[0] or {}
        codec = stream.get("codec_name")
        ch = int(stream.get("channels")) if stream.get("channels") is not None else None
        sr = int(stream.get("sample_rate")) if stream.get("sample_rate") is not None else None
        log.debug("ffprobe: codec=%s ch=%s sr=%s in %.3fs", codec, ch, sr, time.monotonic() - t0)
        return codec, ch, sr
    except Exception:
        log.exception("ffprobe exception")
        return None, None, None


async def convert_to_wav16k_mono(src_path: str, dst_path: Optional[str] = None, threads: int = 0) -> str:
    """
    Конвертирует любой вход в WAV 16k mono PCM s16le.
    Возвращает путь к dst WAV. Если вход уже нужного формата — просто возвращает src_path.
    """
    src = Path(src_path)
    dst = Path(dst_path) if dst_path else (src.with_suffix("").with_name(src.stem + "_16k_mono").with_suffix(".wav"))
    dst.parent.mkdir(parents=True, exist_ok=True)

    codec, ch, sr = await probe_audio(str(src))
    # пропускаем конверт, если уже WAV s16le/mono/16k
    if codec == "pcm_s16le" and ch == 1 and sr == 16000 and src.suffix.lower() == ".wav":
        if dst != src:
            # уже подходящий вход — используем его напрямую
            log.info("Audio already wav/16k/mono — skip convert: %s", src)
            return str(src)

    # быстрый ffmpeg-конверт
    # важные флаги:
    # -nostdin -hide_banner -loglevel error : тише и быстрее
    # -vn -sn -dn : отбросить видео/саб/данные
    # -ac 1 -ar 16000 -sample_fmt s16 : целевой формат
    # -map a:0 : берём первую аудиодорожку
    # -threads N : при желании указать
    cmd = [
        "ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-map", "a:0",
        "-vn", "-sn", "-dn",
        "-ac", "1",
        "-ar", "16000",
        "-sample_fmt", "s16",
        "-acodec", "pcm_s16le",
        str(dst),
    ]
    if threads and threads > 0:
        cmd.insert(1, "-threads"); cmd.insert(2, str(threads))

    log.info("ffmpeg convert → %s", " ".join(shlex.quote(x) for x in cmd))
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        log.error("ffmpeg failed rc=%s err=%s", proc.returncode, err.decode("utf-8", "ignore"))
        raise RuntimeError("ffmpeg convert failed")
    log.info("ffmpeg convert done in %.2fs → %s", time.monotonic() - t0, dst)
    return str(dst)
