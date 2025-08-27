import os
import asyncio
import torch
from pathlib import Path
import torchaudio
from faster_whisper import WhisperModel
from app.services.diarization import diarize
from app.services.embeddings import embed_text
from app.logger import get_logger

log = get_logger(__name__)

MODEL_NAME = "medium"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
log.info(f"Initialising WhisperModel (device={DEVICE})")
whisper = WhisperModel(MODEL_NAME, device=DEVICE)

async def transcribe_with_diarization(audio_path: str) -> list[dict]:
    log.debug(f"Starting transcription pipeline for {audio_path}")
    loop = asyncio.get_running_loop()
    segments: list[dict] = []

    try:
        # 1️⃣ Диаризация
        log.debug("Running diarization")
        speakers = await diarize(audio_path)
        log.info(f"Detected {len(speakers)} speaker(s)")

        # 2️⃣ + 3️⃣ Обрабатываем каждый спикер
        base = Path(audio_path).stem
        tmp_dir = Path("/tmp/diarized")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        wav, sr = torchaudio.load(audio_path)  # один раз загружаем
        log.debug(f"Audio loaded: {audio_path} (sr={sr})")

        for idx, sp in enumerate(speakers):
            start, end = sp["start_ts"], sp["end_ts"]
            start_sample, end_sample = int(start * sr), int(end * sr)
            clip = wav[:, start_sample:end_sample]
            clip_path = tmp_dir / f"{base}_{sp['speaker']}_{idx}.wav"
            torchaudio.save(clip_path, clip, sr)

            # 3️⃣ Whisper – блокирующая операция → run_in_executor
            segs, _ = await loop.run_in_executor(
                None,
                lambda: whisper.transcribe(str(clip_path))
            )
            raw_text = "".join(s.text for s in segs)
            log.debug(f"Whisper generated {len(segs)} sub‑segments, text length={len(raw_text)}")

            # 4️⃣ Embedding – тоже блокирующий, но уже async
            embedding = await embed_text(raw_text)
            if embedding is None:
                log.warning(f"Embedding returned None for speaker {sp['speaker']}")
                # можно пропустить, но вставляем только если есть
            else:
                log.debug(f"Embedding size: {len(embedding)}")

            segments.append({
                "speaker": sp["speaker"],
                "start_ts": start,
                "end_ts": end,
                "text": raw_text,
                "embedding": embedding,
                "segment_id": None,      # заполняем позже в background
            })

            # Удаляем временный файл
            try:
                clip_path.unlink()
                log.debug(f"Deleted clip {clip_path}")
            except OSError as e:
                log.warning(f"Could not delete clip {clip_path}: {e}")

        log.info(f"Finished transcription for {audio_path} – {len(segments)} segments")
        return segments

    except Exception as exc:
        log.exception(f"Error during transcription of {audio_path}")
        raise