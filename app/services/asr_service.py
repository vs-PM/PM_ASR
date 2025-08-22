# app/services/asr_service.py
import os
import torch
from faster_whisper import WhisperModel
from app.services.diarization import diarize
from app.services.embeddings import embed_text

MODEL_NAME = "medium"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
whisper = WhisperModel(MODEL_NAME, device=DEVICE)

async def transcribe_with_diarization(audio_path: str) -> list[dict]:
    # 1) Диаризация
    speakers = await diarize(audio_path)

    # 2) Разделяем файл
    base = Path(audio_path).stem
    tmp_dir = "/tmp/diarized"
    os.makedirs(tmp_dir, exist_ok=True)

    segments = []
    for idx, sp in enumerate(speakers):
        start = sp["start_ts"]
        end = sp["end_ts"]
        # Срез в PyTorch
        wav, sr = torchaudio.load(audio_path)
        start_sample = int(start * sr)
        end_sample = int(end * sr)
        clip = wav[:, start_sample:end_sample]
        clip_path = os.path.join(tmp_dir, f"{base}_{sp['speaker']}_{idx}.wav")
        torchaudio.save(clip_path, clip, sr)

        # 3) Whisper только на этом фрагменте
        segs, _ = whisper.transcribe(clip_path)
        raw_text = "".join(s.text for s in segs)

        segments.append({
            "speaker": sp["speaker"],
            "start_ts": start,
            "end_ts": end,
            "text": raw_text,
            "embedding": await embed_text(raw_text)   # pgvector
        })

        # чистим временный файл
        os.remove(clip_path)

    return segments
